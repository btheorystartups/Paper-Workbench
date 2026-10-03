"""Exact USD upper accounting and request-bound token-count evidence.

Pure policy, no provider or credential access. A tariff is operator evidence, not an
authorization or an assertion that published pricing applies to a particular account.
"""

import json
import re
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation

from .evaluation import AttemptLedger, Denied, digest, encoded

COUNT_FIELDS = frozenset(
    {
        "model",
        "instructions",
        "input",
        "reasoning",
        "text",
        "tool_choice",
        "tools",
        "truncation",
        "parallel_tool_calls",
    }
)
CREATE_FIELDS = COUNT_FIELDS | {"max_output_tokens", "background", "store", "service_tier"}
NANO_USD = 1_000_000_000


def nanos(dollars: str) -> int:
    """Never round an approved dollar ceiling upward or accept binary floats."""
    if type(dollars) is not str or not re.fullmatch(r"[0-9]+(?:\.[0-9]{1,9})?", dollars):
        raise Denied("exact nonnegative USD string required")
    try:
        value = Decimal(dollars) * NANO_USD
    except InvalidOperation:
        raise Denied("invalid USD amount") from None
    if not value.is_finite() or value != value.to_integral_value() or not 0 <= value <= 2**60:
        raise Denied("USD amount outside ledger range")
    return int(value)


def count_payload(body: dict) -> dict:
    """Only direct text and structured text output; remote/file/conversation inputs denied."""
    if (
        type(body) is not dict
        or set(body) - CREATE_FIELDS
        or body.get("tools") != []
        or body.get("tool_choice") != "none"
        or body.get("truncation") != "disabled"
        or body.get("service_tier") != "default"
        or body.get("background") is not True
        or body.get("store") is not False
        or type(body.get("model")) is not str
        or type(body.get("instructions")) is not str
        or type(body.get("input")) is not list
        or type(body.get("max_output_tokens")) is not int
        or not 16 <= body["max_output_tokens"] <= 100_000
    ):
        raise Denied("request outside reviewed cost scope")
    for message in body["input"]:
        if (
            type(message) is not dict
            or set(message) != {"role", "content"}
            or message["role"] not in {"user", "assistant", "system", "developer"}
            or type(message["content"]) is not str
        ):
            raise Denied("only direct text inputs supported")
    return json.loads(encoded({key: value for key, value in body.items() if key in COUNT_FIELDS}))


@dataclass(frozen=True)
class InputCount:
    request_sha256: str
    count_payload_sha256: str
    input_tokens: int
    client_request_id: str
    http_request_id: str

    @classmethod
    def from_response(cls, body, response, *, client_request_id, http_request_id):
        projection = count_payload(body)
        if (
            type(response) is not dict
            or set(response) != {"object", "input_tokens"}
            or response["object"] != "response.input_tokens"
            or type(response["input_tokens"]) is not int
            or not 0 < response["input_tokens"] <= 2**32
            or any(
                type(v) is not str or not re.fullmatch(r"[a-zA-Z0-9_-]{1,128}", v)
                for v in (client_request_id, http_request_id)
            )
        ):
            raise Denied("unverifiable input count")
        return cls(
            digest(encoded(body)),
            digest(encoded(projection)),
            response["input_tokens"],
            client_request_id,
            http_request_id,
        )

    def validate_request(self, body):
        if self.request_sha256 != digest(encoded(body)) or self.count_payload_sha256 != digest(
            encoded(count_payload(body))
        ):
            raise Denied("generation differs from counted request")
        # Validate manually constructed/deserialized records too.
        rebuilt = type(self).from_response(
            body,
            {"object": "response.input_tokens", "input_tokens": self.input_tokens},
            client_request_id=self.client_request_id,
            http_request_id=self.http_request_id,
        )
        if rebuilt != self:
            raise Denied("invalid count record")


@dataclass(frozen=True)
class Tariff:
    model: str
    input_nanos: int
    cached_nanos: int
    cache_write_nanos: int
    output_nanos: int
    auxiliary_request_nanos: int
    source_url: str
    checked_date: str
    account_scope: str
    auxiliary_basis: str

    def validate(self):
        if (
            not isinstance(self.model, str)
            or not self.model
            or any(
                type(v) is not int or not 0 <= v <= 2**40
                for v in (
                    self.input_nanos,
                    self.cached_nanos,
                    self.cache_write_nanos,
                    self.output_nanos,
                    self.auxiliary_request_nanos,
                )
            )
            or self.input_nanos == 0
            or self.output_nanos == 0
            or self.account_scope != "standard-global-text-only"
            or type(self.source_url) is not str
            or not self.source_url.startswith("https://developers.openai.com/")
            or type(self.checked_date) is not str
            or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", self.checked_date)
            or type(self.auxiliary_basis) is not str
            or not self.auxiliary_basis.strip()
        ):
            raise Denied("incomplete tariff evidence")

    @property
    def input_upper_nanos(self):
        # Sum all input-side categories to remain conservative even if their accounting
        # overlaps. This is deliberately an upper estimate, never a precise invoice.
        return self.input_nanos + self.cached_nanos + self.cache_write_nanos

    def reserve(self, body, count: InputCount, *, maximum_auxiliary_requests: int):
        self.validate()
        count.validate_request(body)
        if (
            body["model"] != self.model
            or type(maximum_auxiliary_requests) is not int
            or not 1 <= maximum_auxiliary_requests <= 100
        ):
            raise Denied("tariff/model or auxiliary bound mismatch")
        cost = (
            count.input_tokens * self.input_upper_nanos
            + body["max_output_tokens"] * self.output_nanos
            + maximum_auxiliary_requests * self.auxiliary_request_nanos
        )
        if not 0 < cost <= 2**60:
            raise Denied("reservation outside ledger range")
        return {
            "cost_nanos": cost,
            "tokens": count.input_tokens + body["max_output_tokens"],
            "tariff_sha256": digest(encoded(asdict(self))),
            "count": asdict(count),
            "maximum_auxiliary_requests": maximum_auxiliary_requests,
            "basis": "conservative USD upper bound; not invoice reconciliation",
        }

    def reconcile_upper(self, body, count, usage, *, auxiliary_requests, maximum_auxiliary_requests):
        reservation = self.reserve(body, count, maximum_auxiliary_requests=maximum_auxiliary_requests)
        if (
            type(usage) is not dict
            or type(auxiliary_requests) is not int
            or not 0 <= auxiliary_requests <= maximum_auxiliary_requests
        ):
            raise Denied("usage unavailable")
        inp, out, total = (usage.get(k) for k in ("input_tokens", "output_tokens", "total_tokens"))
        if (
            any(type(v) is not int or v < 0 for v in (inp, out, total))
            or inp != count.input_tokens
            or out > body["max_output_tokens"]
            or total != inp + out
        ):
            raise Denied("observed usage differs from counted request or allowance")
        cost = (
            inp * self.input_upper_nanos
            + out * self.output_nanos
            + auxiliary_requests * self.auxiliary_request_nanos
        )
        assert cost <= reservation["cost_nanos"]
        return {"cost_nanos": cost, "tokens": total, "basis": reservation["basis"]}


class PricedAttempt:
    """Bind conservative USD units to a dedicated ledger, with no dispatch side effect.

    The input-count operation must already have its own durable reservation and
    authorization. This class never assumes that a count/poll/cancel operation is free.
    Ledger ownership and real execution approval remain custodian responsibilities.
    """

    def __init__(
        self,
        ledger: AttemptLedger,
        *,
        attempt_id,
        body,
        count,
        tariff,
        maximum_auxiliary_requests,
        phase="work",
    ):
        import json

        self._ledger = ledger
        self._attempt = attempt_id
        self._body = json.loads(encoded(body))
        self._count = count
        self._tariff = tariff
        self._auxiliary_limit = maximum_auxiliary_requests
        quote = tariff.reserve(self._body, count, maximum_auxiliary_requests=maximum_auxiliary_requests)
        request = {
            "binding_hash": ledger.snapshot()["limits"]["binding_hash"],
            "phase": phase,
            "attempt_id": attempt_id,
            "body": self._body,
            "quote": quote,
            "accounting_unit": "nano_usd_upper",
        }
        ledger.reserve(
            attempt_id,
            digest(encoded(request)),
            quote["cost_nanos"],
            tokens=quote["tokens"],
            phase=phase,
            request=request,
        )

    def dispatch(self):
        self._ledger.dispatch(self._attempt)

    def reconcile(self, usage, *, auxiliary_requests):
        try:
            upper = self._tariff.reconcile_upper(
                self._body,
                self._count,
                usage,
                auxiliary_requests=auxiliary_requests,
                maximum_auxiliary_requests=self._auxiliary_limit,
            )
        except (Denied, TypeError, ValueError):
            self._ledger.reconcile(self._attempt, None)
            raise Denied("cost outcome uncertain; reservation retained") from None
        self._ledger.reconcile(self._attempt, upper["cost_nanos"], tokens=upper["tokens"], result=upper)
        return upper
