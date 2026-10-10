"""Bounded tolerance for terminal telemetry; never an additional task allowance."""


def terminal_overrun_allowance(tokens):
    # Permit a late terminal receipt at most 2% (512 minimum, 2,000 maximum)
    # past a call's slice. The controller still charges it against the shared cap.
    return min(2000, max(512, (tokens + 49) // 50))


TERMINAL_RECEIPT_GRACE_SECONDS = 1.0
