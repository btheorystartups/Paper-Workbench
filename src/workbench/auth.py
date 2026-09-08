"""Authentication and provider-neutral OIDC for local and tenant deployments.

Local mode remains credential-free. When authentication is required, workbench access
tokens are signed and audience-bound, OIDC must be explicitly configured as live, legacy
plaintext development keys are refused, and API credentials are revocable, hashed, scoped,
and bound to one workspace tenant.
"""

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import (
    ApiCredential,
    FederatedIdentity,
    OidcWorkspaceBinding,
    User,
    WorkspaceMember,
)


class AuthError(Exception):
    pass


@dataclass(frozen=True)
class Principal:
    user: User
    workspace_id: str | None
    auth_method: str
    credential_id: str | None = None
    scopes: tuple[str, ...] = ()

    @property
    def id(self) -> str:
        return self.user.id

    @property
    def name(self) -> str:
        return self.user.name

    @property
    def email(self) -> str | None:
        return self.user.email

    @property
    def oidc_subject(self) -> str | None:
        return self.user.oidc_subject


def _email(value: str) -> str:
    return value.strip().lower()


def _pw_bytes(password: str) -> bytes:
    encoded = password.encode("utf-8")
    if len(encoded) > 72:
        raise AuthError("password exceeds bcrypt's 72-byte limit")
    return encoded


def hash_password(password: str) -> str:
    import bcrypt

    return bcrypt.hashpw(_pw_bytes(password), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    import bcrypt

    try:
        return bcrypt.checkpw(_pw_bytes(password), password_hash.encode("ascii"))
    except (AuthError, ValueError, TypeError):
        return False


def _secret() -> str:
    settings = get_settings()
    if settings.auth_required and (
        settings.auth_secret == "dev-insecure-secret" or len(settings.auth_secret) < 32
    ):
        raise AuthError(
            "WB_AUTH_SECRET must be a non-default value of at least 32 characters "
            "when WB_AUTH_REQUIRED=true"
        )
    return settings.auth_secret


def issue_token(
    user_id: str,
    *,
    workspace_id: str | None = None,
    auth_method: str = "password",
    ttl_minutes: int | None = None,
    now: float | None = None,
) -> str:
    import jwt

    settings = get_settings()
    now = now if now is not None else time.time()
    ttl = (ttl_minutes if ttl_minutes is not None else settings.auth_ttl_minutes) * 60
    payload = {
        "sub": user_id,
        "iat": int(now),
        "exp": int(now + ttl),
        "iss": settings.auth_token_issuer,
        "aud": settings.auth_token_audience,
        "jti": secrets.token_hex(16),
        "typ": "access",
        "amr": auth_method,
    }
    if workspace_id:
        payload["wid"] = workspace_id
    return jwt.encode(payload, _secret(), algorithm="HS256")


def decode_access_token(token: str) -> dict:
    import jwt

    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            _secret(),
            algorithms=["HS256"],
            audience=settings.auth_token_audience,
            issuer=settings.auth_token_issuer,
            leeway=max(0, settings.auth_clock_skew_seconds),
            options={
                "require": ["sub", "iat", "exp", "iss", "aud", "jti", "typ"],
                "verify_exp": True,
            },
        )
        if payload.get("typ") != "access":
            raise AuthError("invalid token type")
    except jwt.PyJWTError as exc:
        raise AuthError(f"invalid token: {exc}") from exc
    return payload


def decode_token(token: str, *, now: float | None = None) -> str:
    """Compatibility API returning the subject from a validated access token."""
    del now  # retained for callers of the pre-hardening signature
    return str(decode_access_token(token)["sub"])


def _workspace_for_user(
    session: Session, user_id: str, requested_workspace_id: str | None
) -> str | None:
    memberships = list(
        session.scalars(
            select(WorkspaceMember).where(
                WorkspaceMember.user_id == user_id,
                WorkspaceMember.deleted_at.is_(None),
            )
        )
    )
    if requested_workspace_id:
        if not any(row.workspace_id == requested_workspace_id for row in memberships):
            raise AuthError("workspace membership required")
        return requested_workspace_id
    # Unbound interactive tokens can enumerate only this user's memberships. Clients may
    # request a workspace-bound token explicitly; API credentials are always bound.
    return None


def register_local_user(session: Session, *, name: str, email: str, password: str) -> User:
    normalized_email = _email(email)
    if session.scalars(select(User).where(User.email == normalized_email)).first():
        raise AuthError("email already registered")
    user = User(
        name=name.strip(),
        email=normalized_email,
        password_hash=hash_password(password),
        api_key=None,
        email_verified=False,
    )
    session.add(user)
    session.flush()
    return user


def authorize_registration(session: Session, bootstrap_token: str | None) -> None:
    """Allow open registration only by policy, or one token-gated first-user bootstrap."""
    settings = get_settings()
    if not settings.auth_required or settings.auth_allow_registration:
        return
    existing_user = session.scalars(
        select(User).where(User.deleted_at.is_(None))
    ).first()
    configured = settings.auth_bootstrap_token
    if (
        existing_user is not None
        or len(configured) < 24
        or not bootstrap_token
        or not hmac.compare_digest(bootstrap_token, configured)
    ):
        raise AuthError("self-registration is disabled")


def login_password(
    session: Session,
    *,
    email: str,
    password: str,
    workspace_id: str | None = None,
) -> tuple[User, str]:
    user = session.scalars(
        select(User).where(User.email == _email(email), User.deleted_at.is_(None))
    ).first()
    if user is None or not user.password_hash or not verify_password(password, user.password_hash):
        raise AuthError("invalid email or password")
    selected_workspace = _workspace_for_user(session, user.id, workspace_id)
    return user, issue_token(
        user.id, workspace_id=selected_workspace, auth_method="password"
    )


@dataclass(frozen=True)
class OidcClaims:
    issuer: str
    subject: str
    email: str | None
    name: str | None
    email_verified: bool
    tenant_key: str | None


def _claim_string(payload: dict, key: str) -> str | None:
    if not key:
        return None
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, (str, int)):
        raise AuthError(f"OIDC claim {key!r} must be a string or integer")
    result = str(value).strip()
    return result or None


class OidcVerifier:
    """Verify an OIDC ID token against an explicitly trusted issuer and JWKS."""

    def __init__(
        self,
        *,
        issuer: str,
        audience: str,
        jwks_url: str,
        algorithms: tuple[str, ...],
        tenant_claim: str = "",
        timeout: float = 5.0,
        jwk_client=None,
    ) -> None:
        self._issuer = issuer
        self._audience = audience
        self._jwks_url = jwks_url
        self._algorithms = algorithms
        self._tenant_claim = tenant_claim
        self._timeout = timeout
        if jwk_client is None:
            from jwt import PyJWKClient

            jwk_client = PyJWKClient(
                self._jwks_url,
                cache_keys=True,
                cache_jwk_set=True,
                lifespan=300,
                timeout=self._timeout,
            )
        self._jwk_client = jwk_client

    def verify(self, id_token: str) -> OidcClaims:
        import jwt

        if len(id_token) > 65536:
            raise AuthError("OIDC token is too large")
        try:
            signing_key = self._jwk_client.get_signing_key_from_jwt(id_token)
            payload = jwt.decode(
                id_token,
                signing_key.key,
                algorithms=list(self._algorithms),
                audience=self._audience,
                issuer=self._issuer,
                options={
                    "require": ["iss", "sub", "aud", "iat", "exp"],
                    "verify_exp": True,
                },
            )
        except jwt.PyJWTError as exc:
            raise AuthError(f"OIDC verification failed: {exc}") from exc
        email = _claim_string(payload, "email")
        return OidcClaims(
            issuer=str(payload["iss"]),
            subject=str(payload["sub"]),
            email=_email(email) if email else None,
            name=_claim_string(payload, "name"),
            email_verified=payload.get("email_verified") is True,
            tenant_key=_claim_string(payload, self._tenant_claim),
        )


class FakeOidcVerifier:
    """Offline-only verifier accepting a JSON claims blob as the ID token."""

    def __init__(self, *, issuer: str, tenant_claim: str = "") -> None:
        self._issuer = issuer or "https://fake-oidc.invalid"
        self._tenant_claim = tenant_claim

    def verify(self, id_token: str) -> OidcClaims:
        import json

        try:
            data = json.loads(id_token)
            token_issuer = str(data.get("iss") or self._issuer)
            if token_issuer != self._issuer:
                raise AuthError("fake OIDC issuer mismatch")
            email = _claim_string(data, "email")
            return OidcClaims(
                issuer=token_issuer,
                subject=str(data["sub"]),
                email=_email(email) if email else None,
                name=_claim_string(data, "name"),
                email_verified=data.get("email_verified") is True,
                tenant_key=_claim_string(data, self._tenant_claim),
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise AuthError(f"invalid fake OIDC token: {exc}") from exc


def _validate_oidc_url(value: str, label: str) -> str:
    settings = get_settings()
    parsed = urlparse(value)
    allowed_schemes = {"https"} if settings.oidc_require_https else {"http", "https"}
    if parsed.scheme not in allowed_schemes or not parsed.hostname:
        scheme_label = "HTTPS" if settings.oidc_require_https else "HTTP(S)"
        raise AuthError(f"{label} must be an absolute {scheme_label} URL")
    if parsed.username or parsed.password or parsed.fragment:
        raise AuthError(f"{label} must not contain credentials or a fragment")
    return value


@lru_cache(maxsize=8)
def _live_oidc_verifier(
    issuer: str,
    audience: str,
    jwks_url: str,
    algorithms: tuple[str, ...],
    tenant_claim: str,
    timeout: float,
) -> OidcVerifier:
    return OidcVerifier(
        issuer=issuer,
        audience=audience,
        jwks_url=jwks_url,
        algorithms=algorithms,
        tenant_claim=tenant_claim,
        timeout=timeout,
    )


def get_oidc_verifier():
    settings = get_settings()
    mode = settings.oidc_mode.strip().lower()
    if mode == "disabled":
        raise AuthError("OIDC login is disabled")
    if mode == "fake":
        if settings.auth_required:
            raise AuthError("fake OIDC is refused when WB_AUTH_REQUIRED=true")
        return FakeOidcVerifier(
            issuer=settings.oidc_issuer,
            tenant_claim=settings.oidc_tenant_claim,
        )
    if mode != "live":
        raise AuthError("WB_OIDC_MODE must be disabled, fake, or live")
    if not settings.oidc_issuer or not settings.oidc_audience or not settings.oidc_jwks_url:
        raise AuthError("live OIDC requires issuer, audience, and JWKS URL")
    issuer = _validate_oidc_url(settings.oidc_issuer, "OIDC issuer")
    jwks_url = _validate_oidc_url(settings.oidc_jwks_url, "OIDC JWKS URL")
    allowed = {"RS256", "RS384", "RS512", "ES256", "ES384", "ES512"}
    algorithms = tuple(
        item.strip() for item in settings.oidc_allowed_algorithms.split(",") if item.strip()
    )
    if not algorithms or any(item not in allowed for item in algorithms):
        raise AuthError("OIDC algorithms must be an explicit asymmetric RS*/ES* allowlist")
    return _live_oidc_verifier(
        issuer,
        settings.oidc_audience,
        jwks_url,
        algorithms,
        settings.oidc_tenant_claim,
        max(0.1, settings.oidc_jwks_timeout_seconds),
    )


def validate_auth_configuration() -> None:
    """Validate deployment security settings without contacting the identity provider."""
    settings = get_settings()
    if settings.auth_required:
        _secret()
        if not settings.auth_token_issuer.strip() or not settings.auth_token_audience.strip():
            raise AuthError("auth token issuer and audience must be non-empty")
        if not 1 <= settings.auth_ttl_minutes <= 1440:
            raise AuthError("WB_AUTH_TTL_MINUTES must be between 1 and 1440")
        if not 0 <= settings.auth_clock_skew_seconds <= 300:
            raise AuthError("WB_AUTH_CLOCK_SKEW_SECONDS must be between 0 and 300")
        if settings.oidc_mode.strip().lower() == "fake":
            raise AuthError("fake OIDC is refused when WB_AUTH_REQUIRED=true")
    if settings.oidc_mode.strip().lower() == "live":
        if settings.oidc_allow_jit_membership and not settings.oidc_tenant_claim:
            raise AuthError("OIDC JIT membership requires WB_OIDC_TENANT_CLAIM")
        get_oidc_verifier()


def login_oidc(
    session: Session, id_token: str, *, workspace_id: str | None = None
) -> tuple[User, str]:
    from .services import security

    settings = get_settings()
    claims = get_oidc_verifier().verify(id_token)
    identity = session.scalars(
        select(FederatedIdentity).where(
            FederatedIdentity.issuer == claims.issuer,
            FederatedIdentity.subject == claims.subject,
            FederatedIdentity.deleted_at.is_(None),
        )
    ).first()
    user = session.get(User, identity.user_id) if identity else None
    if identity is not None and (user is None or user.deleted_at is not None):
        raise AuthError("OIDC identity is linked to a disabled account")
    if user is None and claims.email:
        email_user = session.scalars(
            select(User).where(User.email == claims.email, User.deleted_at.is_(None))
        ).first()
        if email_user and claims.email_verified and settings.oidc_allow_email_linking:
            user = email_user
        elif email_user:
            raise AuthError("OIDC email belongs to an existing account; pre-link required")
    if user is None:
        if not settings.oidc_allow_jit_provisioning:
            raise AuthError("OIDC identity is not provisioned")
        user = User(
            name=claims.name or claims.email or "oidc-user",
            email=claims.email if claims.email_verified else None,
            api_key=None,
            email_verified=claims.email_verified,
        )
        session.add(user)
        session.flush()
    if identity is None:
        identity = FederatedIdentity(
            user_id=user.id,
            issuer=claims.issuer,
            subject=claims.subject,
            email_at_link=claims.email if claims.email_verified else None,
        )
        session.add(identity)
    identity.last_login_at = datetime.now(UTC)

    selected_workspace = workspace_id
    if claims.tenant_key:
        binding = session.scalars(
            select(OidcWorkspaceBinding).where(
                OidcWorkspaceBinding.issuer == claims.issuer,
                OidcWorkspaceBinding.tenant_key == claims.tenant_key,
                OidcWorkspaceBinding.deleted_at.is_(None),
            )
        ).first()
        if binding is None:
            raise AuthError("OIDC tenant claim is not bound to a workspace")
        if selected_workspace and selected_workspace != binding.workspace_id:
            raise AuthError("requested workspace does not match OIDC tenant claim")
        selected_workspace = binding.workspace_id
        membership = security.workspace_role_of(session, selected_workspace, user.id)
        if membership is None:
            if not settings.oidc_allow_jit_membership:
                raise AuthError("OIDC workspace membership is not provisioned")
            if binding.default_role not in {"viewer", "member"}:
                raise AuthError("OIDC JIT binding has an unsafe workspace role")
            security.add_workspace_member(
                session, selected_workspace, user.id, binding.default_role
            )
    selected_workspace = _workspace_for_user(session, user.id, selected_workspace)
    return user, issue_token(
        user.id, workspace_id=selected_workspace, auth_method="oidc"
    )


_API_SCOPES = {"read", "write", "admin"}


def _api_key_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_api_credential(
    session: Session,
    *,
    user_id: str,
    workspace_id: str,
    name: str,
    scopes: list[str],
    expires_at: datetime | None = None,
) -> tuple[ApiCredential, str]:
    if not name.strip():
        raise AuthError("API key name is required")
    normalized = sorted(set(scopes))
    if not normalized or any(scope not in _API_SCOPES for scope in normalized):
        raise AuthError(f"API key scopes must be a non-empty subset of {sorted(_API_SCOPES)}")
    if "admin" in normalized:
        normalized = sorted(set(normalized) | {"read", "write"})
    elif "write" in normalized:
        normalized = sorted(set(normalized) | {"read"})
    token = f"wbk_{secrets.token_urlsafe(32)}"
    credential = ApiCredential(
        user_id=user_id,
        workspace_id=workspace_id,
        name=name.strip(),
        key_prefix=token[:12],
        key_hash=_api_key_hash(token),
        scopes=normalized,
        expires_at=expires_at,
    )
    session.add(credential)
    session.flush()
    return credential, token


def _credential_principal(session: Session, token: str) -> Principal | None:
    if not token.startswith("wbk_") or len(token) > 256:
        return None
    credential = session.scalars(
        select(ApiCredential).where(
            ApiCredential.key_hash == _api_key_hash(token),
            ApiCredential.deleted_at.is_(None),
            ApiCredential.revoked_at.is_(None),
        )
    ).first()
    if credential is None:
        return None
    now = datetime.now(UTC)
    expires_at = credential.expires_at
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at and expires_at <= now:
        return None
    user = session.get(User, credential.user_id)
    if user is None or user.deleted_at is not None:
        return None
    credential.last_used_at = now
    return Principal(
        user=user,
        workspace_id=credential.workspace_id,
        auth_method="api_key",
        credential_id=credential.id,
        scopes=tuple(credential.scopes),
    )


def principal_from_bearer(session: Session, token: str | None) -> Principal:
    """Resolve a bearer token without accepting local development keys in production."""
    from .services import security

    settings = get_settings()
    if not token:
        if settings.auth_required:
            raise AuthError("authentication required")
        return Principal(security.default_user(session), None, "local")

    credential_principal = _credential_principal(session, token)
    if credential_principal:
        return credential_principal

    try:
        payload = decode_access_token(token)
        user = session.get(User, str(payload["sub"]))
        if user is None or user.deleted_at is not None:
            raise AuthError("token subject not found")
        workspace_id = payload.get("wid")
        if workspace_id and not isinstance(workspace_id, str):
            raise AuthError("invalid workspace claim")
        return Principal(
            user=user,
            workspace_id=workspace_id,
            auth_method=str(payload.get("amr") or "token"),
        )
    except AuthError:
        if not settings.auth_required:
            user = session.scalars(
                select(User).where(User.api_key == token, User.deleted_at.is_(None))
            ).first()
            if user:
                return Principal(user, None, "legacy_api_key")
        raise AuthError("invalid bearer token") from None


def require_api_scope(principal: Principal, required: str) -> None:
    if principal.auth_method != "api_key":
        return
    if required not in principal.scopes:
        raise AuthError(f"API credential lacks {required!r} scope")
