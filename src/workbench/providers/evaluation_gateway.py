"""Data-only gateway permit: no arbitrary URLs, headers, credentials or HTTP client.

Custodian supplies an exact request hash and operation bound. Provider IDs become
usable only after a successful create acknowledgement. This does not authorize live
dispatch or make the caller an OS sandbox.
"""

import json
import re
import threading
from dataclasses import asdict

from ..services.evaluation import Denied, digest, encoded
from ..services.evaluation_costs import InputCount, PricedAttempt, count_payload


class GatewayPermit:
    def __init__(self, body, *, maximum_operations):
        count_payload(body)
        if type(maximum_operations) is not int or not 2 <= maximum_operations <= 100:
            raise Denied("invalid operation limit")
        self._body = encoded(body)
        self._request_hash = digest(self._body)
        self._maximum = maximum_operations
        self._operations = 0
        self._ids = set()
        self._counted = False
        self._created = False
        self._response_id = None
        self._pending = None
        self._failed = False

    def admit(self, message):
        if (
            self._failed
            or self._pending
            or self._operations >= self._maximum
            or type(message) is not dict
            or set(message) != {"operation", "client_request_id", "request_sha256", "payload"}
            or message["request_sha256"] != self._request_hash
        ):
            raise Denied("gateway request denied")
        identifier, operation, payload = (
            message["client_request_id"],
            message["operation"],
            message["payload"],
        )
        if (
            type(identifier) is not str
            or not re.fullmatch(r"[a-zA-Z0-9_-]{1,128}", identifier)
            or identifier in self._ids
        ):
            raise Denied("gateway request identity denied")
        if operation == "count" and not self._counted and not self._created:
            if encoded(payload) != encoded(count_payload(json.loads(self._body))):
                raise Denied("count payload mismatch")
            method, path = "POST", "/v1/responses/input_tokens"
        elif operation == "create" and self._counted and not self._created:
            if encoded(payload) != self._body:
                raise Denied("generation payload mismatch")
            method, path = "POST", "/v1/responses"
        elif operation in {"retrieve", "cancel"} and self._response_id is not None:
            if payload != {"response_id": self._response_id}:
                raise Denied("response does not belong to this attempt")
            method = "GET" if operation == "retrieve" else "POST"
            path = "/v1/responses/" + self._response_id + ("/cancel" if operation == "cancel" else "")
        else:
            raise Denied("gateway operation denied")
        self._ids.add(identifier)
        self._operations += 1
        self._pending = operation
        return {
            "method": method,
            "path": path,
            "client_request_id": identifier,
            "payload": json.loads(encoded(payload)),
            "request_sha256": self._request_hash,
        }

    def acknowledge(self, *, success, response_id=None):
        operation = self._pending
        if not operation:
            raise Denied("no operation pending")
        self._pending = None
        if success is not True:
            self._failed = True
            return
        if operation == "count":
            self._counted = True
        elif operation == "create":
            if not isinstance(response_id, str) or not re.fullmatch(
                r"resp_[a-zA-Z0-9_-]{1,120}", response_id
            ):
                self._failed = True
                raise Denied("invalid provider response identity")
            self._created = True
            self._response_id = response_id


def usd_binding(tariff, run_binding):
    """Bind a dedicated ledger to its USD unit, tariff, and frozen run identity."""
    tariff.validate()
    if type(run_binding) is not str or not re.fullmatch(r"[0-9a-f]{64}", run_binding):
        raise Denied("invalid run binding")
    return digest(encoded({"unit": "nano_usd_upper", "tariff": asdict(tariff), "run": run_binding}))


class BudgetedGateway:
    """Serial custodian policy; returns data-only routes after durable reservation.

    This has no HTTP client, credential access, recovery/redispatch, or live factory.
    The trusted dispatcher supplies count evidence and verified terminal usage.
    Count fees have their own reservation; poll/cancel fees belong to generation.
    """

    def __init__(self, body, *, ledger, tariff, run_binding, attempt_id, maximum_operations, phase="work"):
        if type(maximum_operations) is not int or not 3 <= maximum_operations <= 100:
            raise Denied("invalid operation limit")
        if type(attempt_id) is not str or not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", attempt_id):
            raise Denied("invalid attempt identity")
        self._binding = usd_binding(tariff, run_binding)
        if ledger.snapshot()["limits"]["binding_hash"] != self._binding:
            raise Denied("ledger has different run, tariff or accounting units")
        self._permit = GatewayPermit(body, maximum_operations=maximum_operations)
        self._body = json.loads(encoded(body))
        self._ledger, self._tariff = ledger, tariff
        self._attempt, self._phase = attempt_id, phase
        self._auxiliary_limit = maximum_operations - 2
        self._count = self._priced = self._pending = None
        self._auxiliary_requests = 0
        self._closed = False
        self._lock = threading.Lock()

    def admit(self, message):
        with self._lock:
            if self._closed:
                raise Denied("gateway closed")
            route = self._permit.admit(message)
            operation = message["operation"]
            try:
                if operation == "count":
                    request = {
                        "binding_hash": self._binding,
                        "phase": self._phase,
                        "attempt_id": self._attempt + "-count",
                        "route": route,
                    }
                    self._ledger.reserve(
                        self._attempt + "-count",
                        digest(encoded(request)),
                        max(1, self._tariff.auxiliary_request_nanos),
                        tokens=0,
                        phase=self._phase,
                        request=request,
                    )
                    self._ledger.dispatch(self._attempt + "-count")
                elif operation == "create":
                    self._priced = PricedAttempt(
                        self._ledger,
                        attempt_id=self._attempt,
                        body=self._body,
                        count=self._count,
                        tariff=self._tariff,
                        maximum_auxiliary_requests=self._auxiliary_limit,
                        phase=self._phase,
                    )
                    self._priced.dispatch()
                else:
                    self._auxiliary_requests += 1
            except Exception:
                self._closed = True
                raise
            self._pending = (operation, route["client_request_id"])
            return route

    def acknowledge(self, *, success, result=None, http_request_id=None):
        with self._lock:
            if self._closed or self._pending is None:
                raise Denied("no operation pending")
            operation, client_id = self._pending
            self._pending = None
            try:
                if success is not True:
                    raise Denied("upstream outcome unknown")
                if operation == "count":
                    self._count = InputCount.from_response(
                        self._body, result, client_request_id=client_id, http_request_id=http_request_id
                    )
                    self._ledger.reconcile(
                        self._attempt + "-count",
                        self._tariff.auxiliary_request_nanos,
                        tokens=0,
                        result=asdict(self._count),
                    )
                self._permit.acknowledge(
                    success=True, response_id=result.get("id") if type(result) is dict else None
                )
            except Exception:
                self._closed = True
                self._ledger.reconcile(
                    self._attempt + "-count" if operation == "count" else self._attempt, None
                )
                raise Denied("upstream evidence invalid; reservation retained") from None

    def settle(self, usage):
        """Caller must verify terminal status/model/policy before supplying usage."""
        with self._lock:
            if self._closed or self._pending is not None or self._priced is None:
                raise Denied("generation cannot be settled")
            self._closed = True
            return self._priced.reconcile(usage, auxiliary_requests=self._auxiliary_requests)
