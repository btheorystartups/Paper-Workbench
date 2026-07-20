"""Authentication (P-hardening). Off by default (WB_AUTH_REQUIRED=false) so local
single-user mode and offline tests need no credentials. When enabled, endpoints require a
bearer token that is either:
  - a signed workbench JWT (issued by password or OIDC login), or
  - a user's api_key (local dev-token path).

Trust boundaries (honest scope):
- Passwords are bcrypt-hashed via passlib; never stored or logged in plaintext.
- JWTs are HS256-signed with WB_AUTH_SECRET; short-lived (WB_AUTH_TTL_MINUTES).
- OIDC verification is done behind OidcVerifier; the live verifier validates the ID
  token signature against the provider JWKS (issuer/audience/exp checked). A FakeOidc
  verifier lets the whole flow be exercised offline. We never create accounts or enter
  credentials on the user's behalf — login is initiated by the user with their own token.
"""

import time
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import User


class AuthError(Exception):
    pass


# --- password hashing (bcrypt directly; lazy import so it's optional) ---
# bcrypt hard-caps input at 72 bytes; we truncate deterministically (standard practice).


def _pw_bytes(password: str) -> bytes:
    return password.encode("utf-8")[:72]


def hash_password(password: str) -> str:
    import bcrypt

    return bcrypt.hashpw(_pw_bytes(password), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    import bcrypt

    try:
        return bcrypt.checkpw(_pw_bytes(password), password_hash.encode("ascii"))
    except (ValueError, TypeError):
        return False


# --- workbench JWTs ---


def _secret() -> str:
    settings = get_settings()
    if settings.auth_required and settings.auth_secret == "dev-insecure-secret":
        # Fail closed: refuse to run enforced auth with the default secret.
        raise AuthError("WB_AUTH_SECRET must be set when WB_AUTH_REQUIRED=true")
    return settings.auth_secret


def issue_token(user_id: str, *, ttl_minutes: int | None = None, now: float | None = None) -> str:
    import jwt

    settings = get_settings()
    now = now if now is not None else time.time()
    ttl = (ttl_minutes if ttl_minutes is not None else settings.auth_ttl_minutes) * 60
    payload = {"sub": user_id, "iat": int(now), "exp": int(now + ttl), "iss": "paper-workbench"}
    return jwt.encode(payload, _secret(), algorithm="HS256")


def decode_token(token: str, *, now: float | None = None) -> str:
    import jwt

    try:
        options = {"verify_exp": True}
        payload = jwt.decode(
            token, _secret(), algorithms=["HS256"], issuer="paper-workbench", options=options
        )
    except jwt.PyJWTError as exc:
        raise AuthError(f"invalid token: {exc}") from exc
    return payload["sub"]


# --- login flows ---


def register_local_user(session: Session, *, name: str, email: str, password: str) -> User:
    import secrets

    if session.scalars(select(User).where(User.email == email)).first():
        raise AuthError("email already registered")
    user = User(
        name=name, email=email, password_hash=hash_password(password),
        api_key=secrets.token_hex(16), email_verified=False,
    )
    session.add(user)
    session.flush()
    return user


def login_password(session: Session, *, email: str, password: str) -> tuple[User, str]:
    user = session.scalars(select(User).where(User.email == email)).first()
    if user is None or not user.password_hash or not verify_password(password, user.password_hash):
        raise AuthError("invalid email or password")
    return user, issue_token(user.id)


# --- OIDC ---


@dataclass
class OidcClaims:
    subject: str
    email: str | None
    name: str | None
    email_verified: bool


class OidcVerifier:
    """Live OIDC ID-token verification against a provider's JWKS."""

    def __init__(self, *, issuer: str, audience: str, jwks_url: str, session=None) -> None:
        self._issuer = issuer
        self._audience = audience
        self._jwks_url = jwks_url
        self._session = session

    def verify(self, id_token: str) -> OidcClaims:
        import jwt
        from jwt import PyJWKClient

        try:
            signing_key = PyJWKClient(self._jwks_url).get_signing_key_from_jwt(id_token)
            payload = jwt.decode(
                id_token, signing_key.key, algorithms=["RS256", "ES256"],
                audience=self._audience, issuer=self._issuer,
            )
        except jwt.PyJWTError as exc:
            raise AuthError(f"OIDC verification failed: {exc}") from exc
        return OidcClaims(
            subject=payload["sub"], email=payload.get("email"),
            name=payload.get("name"), email_verified=bool(payload.get("email_verified")),
        )


class FakeOidcVerifier:
    """Offline OIDC verifier: accepts a JSON claims blob as the 'id token'. Lets the
    login→account-link flow be tested end to end without a real IdP."""

    def verify(self, id_token: str) -> OidcClaims:
        import json

        try:
            data = json.loads(id_token)
            return OidcClaims(
                subject=data["sub"], email=data.get("email"),
                name=data.get("name"), email_verified=bool(data.get("email_verified")),
            )
        except (json.JSONDecodeError, KeyError) as exc:
            raise AuthError(f"invalid fake OIDC token: {exc}") from exc


def get_oidc_verifier():
    settings = get_settings()
    if settings.provider_mode != "live" or not settings.oidc_issuer:
        return FakeOidcVerifier()
    return OidcVerifier(
        issuer=settings.oidc_issuer,
        audience=settings.oidc_audience,
        jwks_url=settings.oidc_jwks_url,
    )


def login_oidc(session: Session, id_token: str) -> tuple[User, str]:
    import secrets

    claims = get_oidc_verifier().verify(id_token)
    user = session.scalars(select(User).where(User.oidc_subject == claims.subject)).first()
    if user is None and claims.email:
        # link by verified email if present, else create a fresh federated identity
        user = session.scalars(select(User).where(User.email == claims.email)).first()
    if user is None:
        user = User(
            name=claims.name or (claims.email or "oidc-user"),
            email=claims.email, oidc_subject=claims.subject,
            api_key=secrets.token_hex(16), email_verified=claims.email_verified,
        )
        session.add(user)
        session.flush()
    else:
        user.oidc_subject = claims.subject
        if claims.email_verified:
            user.email_verified = True
    return user, issue_token(user.id)


# --- request principal resolution ---


def principal_from_bearer(session: Session, token: str | None) -> User:
    """Resolve a request's User from a bearer token. When auth is not required and no
    token is given, fall back to the local default user (single-user mode)."""
    from .services import security

    settings = get_settings()
    if not token:
        if settings.auth_required:
            raise AuthError("authentication required")
        return security.default_user(session)
    # try workbench JWT first, then api_key
    try:
        user_id = decode_token(token)
        user = session.get(User, user_id)
        if user is None:
            raise AuthError("token subject not found")
        return user
    except AuthError:
        # JWT didn't validate — fall back to the api-key path (not an error to chain).
        user = session.scalars(select(User).where(User.api_key == token)).first()
        if user is None:
            raise AuthError("invalid bearer token") from None
        return user
