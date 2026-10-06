"""Version-bound offline counter transport review; not live capability attestation."""

REVIEWED_RUNTIME_VERSION = "0.160.1"
COUNTER_FAILURE_REASONS = frozenset(
    {
        "unreviewed_runtime",
        "model_requires_code_mode",
        "unreviewed_model",
    }
)


class CounterCompatibilityError(ValueError):
    def __init__(self, reason):
        if reason not in COUNTER_FAILURE_REASONS:
            raise ValueError("unknown counter compatibility reason")
        self.reason = reason
        super().__init__("counter transport incompatible: " + reason)


def counter_capability(model, runtime_version):
    if runtime_version != REVIEWED_RUNTIME_VERSION:
        raise CounterCompatibilityError("unreviewed_runtime")
    if model not in {"gpt-5.6-sol", "gpt-5.5"}:
        raise CounterCompatibilityError("unreviewed_model")
    return {
        "runtime_version": REVIEWED_RUNTIME_VERSION,
        "model": model,
        "reviewed_dispatch": "direct_namespaced_function",
        "verification": "pinned_runtime_offline",
        "successful_invocation_received": False,
    }
