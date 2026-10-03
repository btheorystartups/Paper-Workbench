"""Local invocation authorization. The gate is never passed to the Codex runtime."""

import ipaddress
import secrets
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from uuid import UUID

from ..config import get_settings

LOCAL_NOTICE = (
    "Local single-user Codex: usage belongs to the ChatGPT account authenticated in "
    "this instance's isolated Codex profile. The gate does not select the billed account. "
    "Text limits and cancellation do not guarantee account-usage ceilings."
)


class CodexLocalError(RuntimeError):
    """Safe, application-owned message; never wrap provider text in this exception."""

    status_code = 503


class CodexGateError(CodexLocalError):
    status_code = 403


class CodexLimitError(CodexLocalError):
    status_code = 413


class CodexTimeoutError(CodexLocalError):
    status_code = 504


_authorized: ContextVar[bool] = ContextVar("codex_local_authorized", default=False)
# Set only by the loopback launcher after it has bound its own listening socket.
_loopback_listener_verified = False


def is_loopback(value: str | None) -> bool:
    try:
        return ipaddress.ip_address(value or "").is_loopback
    except ValueError:
        return False


def validate_configuration(settings=None) -> None:
    settings = settings or get_settings()
    if not settings.codex_local_enabled:
        raise CodexLocalError("codex_local is disabled; explicit local opt-in is required")
    if (
        settings.deployment_mode != "local"
        or settings.auth_required
        or settings.auth_allow_registration
        or settings.auth_cookie_sessions_enabled
        or settings.oidc_mode != "disabled"
    ):
        raise CodexLocalError("codex_local requires a local single-user deployment")
    if len(settings.codex_local_gate_secret.get_secret_value()) < 32:
        raise CodexLocalError("codex_local requires a gate secret of at least 32 characters")
    secret = settings.codex_local_gate_secret.get_secret_value()
    if any(secret in value for value in (
        settings.codex_local_home, settings.codex_local_account_email, settings.codex_local_workspace_id,
        settings.codex_local_model, settings.codex_local_reasoning_effort,
    )):
        raise CodexLocalError("codex_local gate must be independent of runtime configuration")
    profile = Path(settings.codex_local_home)
    if not settings.codex_local_home or not profile.is_absolute():
        raise CodexLocalError("codex_local requires an absolute isolated profile directory")
    # No reads of the profile's credential or configuration files.
    if profile.resolve() == (Path.home() / ".codex").resolve():
        raise CodexLocalError("codex_local must not use the default Codex profile")
    if not settings.codex_local_account_email.strip():
        raise CodexLocalError("codex_local requires the expected ChatGPT account email")
    if settings.codex_local_workspace_id:
        try:
            UUID(settings.codex_local_workspace_id)
        except (ValueError, AttributeError):
            raise CodexLocalError("codex_local workspace restriction must be a UUID") from None
    from .protocols import validate_reasoning_effort

    validate_reasoning_effort(settings.codex_local_reasoning_effort)


def require_access(settings=None) -> None:
    validate_configuration(settings)
    if not _loopback_listener_verified:
        raise CodexLocalError("codex_local requires the workbench.codex_local_server loopback launcher")
    if not _authorized.get():
        raise CodexGateError("codex_local gate is missing or invalid")


@contextmanager
def gate_scope(value: str | None, *, local_request: bool, settings=None):
    """Store only an authorization boolean in context, never the supplied gate."""
    settings = settings or get_settings()
    expected = settings.codex_local_gate_secret.get_secret_value()
    matched = secrets.compare_digest((value or "").encode("utf-8"), expected.encode("utf-8"))
    token = _authorized.set(bool(local_request and expected and matched))
    try:
        yield
    finally:
        _authorized.reset(token)
