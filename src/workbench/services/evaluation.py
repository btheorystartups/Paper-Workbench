"""Offline diagnostic broker. No project retrieval, host paths, network or providers.

This is a data-only tool boundary, not a sandbox for arbitrary Python plugins.
Live provider dispatch is deliberately unavailable until runtime and accounting
integration have been independently validated. Custodians supply exactly two bytestrings.
"""

import hashlib
import json
import re
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path

INPUTS = frozenset({"inputs/manuscript.tex", "inputs/historical_verification_record.txt"})
POLICY = "two-input-diagnostic-v1"


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def encoded(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


class Denied(ValueError):
    """Generic errors deliberately omit denied arguments and hidden content."""


class BudgetDenied(Denied):
    """No dispatch occurred; protected verification may still be available."""


class Diagnostic:
    def __init__(self, inputs: dict[str, bytes], expected: dict[str, str], *, brief: str):
        if set(inputs) != INPUTS or set(expected) != INPUTS:
            raise Denied("input set denied")
        if any(
            type(v) is not bytes or len(v) > 4_000_000 or digest(v) != expected[k] for k, v in inputs.items()
        ):
            raise Denied("input identity denied")
        self._inputs = dict(inputs)
        self._namespace = uuid.uuid4().hex
        self._manifest = {
            "policy": POLICY,
            "namespace": self._namespace,
            "inputs": dict(expected),
            "brief_sha256": digest(brief.encode()),
            "provider": "disabled",
            "conversation": "fresh",
            "network": "denied",
        }
        self._trace = []
        self._cache = {}
        self._messages = [{"role": "user", "content": brief}]
        self._frozen = False

    @property
    def namespace(self):
        return self._namespace

    def participant_context(self) -> dict:
        """Detached, allowlisted provider context; never includes a host path or prior chat."""
        if self._frozen:
            raise Denied("run frozen")
        return json.loads(encoded({"manifest": self._manifest, "messages": self._messages}))

    def tool(self, name: str, **args):
        if self._frozen or len(self._trace) >= 1000:
            raise Denied("run frozen")
        try:
            result = self._dispatch(name, args)
        except (KeyError, TypeError, ValueError, UnicodeError):
            # Neither path, query, supplied secret nor denied tool name goes in the log.
            self._trace.append({"event": "tool_denied"})
            raise Denied("tool request denied") from None
        self._trace.append(
            {
                "event": "tool",
                "name": name,
                "request_sha256": digest(encoded(args)),
                "result_sha256": digest(encoded(result)),
            }
        )
        return result

    def _dispatch(self, name, args):
        if name == "read" and set(args) == {"alias"}:
            return self._inputs[args["alias"]].decode("utf-8")
        if name == "retrieve" and set(args) == {"query"} and isinstance(args["query"], str):
            query = args["query"]
            if not 0 < len(query) <= 512:
                raise Denied()
            return [
                {"alias": alias, "line": i, "text": line}
                for alias, content in sorted(self._inputs.items())
                for i, line in enumerate(content.decode("utf-8").splitlines(), 1)
                if query.casefold() in line.casefold()
            ][:100]
        if name == "cache_get" and set(args) == {"namespace", "key"}:
            if args["namespace"] != self._namespace:
                raise Denied()
            return json.loads(encoded(self._cache.get(args["key"])))
        if name == "cache_put" and set(args) == {"namespace", "key", "value"}:
            if args["namespace"] != self._namespace or len(encoded(args)) > 16_000:
                raise Denied()
            self._cache[args["key"]] = json.loads(encoded(args["value"]))
            return True
        if name == "conversation" and not args:
            return json.loads(encoded(self._messages))
        raise Denied()

    def freeze(self, outputs: dict[str, bytes]) -> bytes:
        if self._frozen or not outputs or len(outputs) > 20 or "receipt.json" in outputs:
            raise Denied("output freeze denied")
        if any(
            not re.fullmatch(r"[a-zA-Z0-9_-]+\.(?:txt|tex|json|md)", name)
            or type(payload) is not bytes
            or len(payload) > 4_000_000
            for name, payload in outputs.items()
        ):
            raise Denied("output set denied")
        receipt = {
            "manifest": self._manifest,
            "input_manifest_sha256": digest(encoded(self._manifest)),
            "outputs": {k: {"sha256": digest(v), "bytes": len(v)} for k, v in sorted(outputs.items())},
            "trace": self._trace,
            "trace_sha256": digest(encoded(self._trace)),
            "status": "offline_diagnostic_only",
            "live_ready": False,
        }
        self._frozen = True
        return encoded(receipt)


def capture(directory: Path, receipt: bytes, outputs: dict[str, bytes]) -> None:
    """Custodian-only exclusive capture. Never accepts participant-selected paths.

    Receipt hashes authenticate the captured bytes, not scientific correctness.
    Existing directories and any reparse-point ancestor are refused.
    """
    directory = Path(directory).absolute()
    for parent in [directory, *directory.parents]:
        if parent.is_symlink() or parent.is_junction():
            raise Denied("capture path denied")
    data = json.loads(receipt)
    declared = data["outputs"]
    if (
        "receipt.json" in outputs
        or set(outputs) != set(declared)
        or any(
            not re.fullmatch(r"[a-zA-Z0-9_-]+\.(?:txt|tex|json|md)", name)
            or digest(value) != declared[name]["sha256"]
            or len(value) != declared[name]["bytes"]
            for name, value in outputs.items()
        )
    ):
        raise Denied("capture identity denied")
    directory.mkdir(exist_ok=False)
    for name, value in {**outputs, "receipt.json": receipt}.items():
        with (directory / name).open("xb") as stream:
            stream.write(value)


class AttemptLedger:
    """Dedicated durable reservation ledger, independent of caller DB transactions.

    Integer cost units; callers must reserve a worst-case bound before dispatch.
    A pending/uncertain attempt continues to consume its full reservation. An attempt
    ID is never dispatched twice. Bound adapter ledgers also reserve token units and
    protected verification allocations. No live provider is wired to this component.
    """

    def __init__(self, path: Path):
        self.path = Path(path).absolute()

    @contextmanager
    def _connection(self):
        if not self.path.is_file() or any(
            p.is_symlink() or p.is_junction() for p in [self.path, *self.path.parents]
        ):
            raise Denied("ledger path denied")
        connection = sqlite3.connect(self.path.as_uri() + "?mode=rw", uri=True, timeout=10)
        try:
            if connection.execute("PRAGMA user_version").fetchone()[0] != 2:
                raise Denied("unsupported ledger version; no automatic migration")
            with connection:
                yield connection
        finally:
            connection.close()

    @classmethod
    def create(
        cls,
        path: Path,
        *,
        ceiling: int,
        token_ceiling: int | None = None,
        cost_reserve: int = 0,
        token_reserve: int = 0,
        binding_hash: str = "",
    ):
        if type(ceiling) is not int or not 0 < ceiling <= 2**60:
            raise Denied("invalid ceiling")
        if (
            token_ceiling is not None
            and (type(token_ceiling) is not int or not 0 < token_ceiling <= 2**60)
            or type(cost_reserve) is not int
            or not 0 <= cost_reserve <= ceiling
            or type(token_reserve) is not int
            or not 0 <= token_reserve <= (token_ceiling or 0)
            or binding_hash
            and not re.fullmatch(r"[0-9a-f]{64}", binding_hash)
        ):
            raise Denied("invalid reservation policy")
        path = Path(path).absolute()
        if any(p.is_symlink() or p.is_junction() for p in [path, *path.parents]):
            raise Denied("ledger path denied")
        with path.open("xb"):
            pass
        connection = sqlite3.connect(path)
        try:
            with connection:
                connection.executescript("""
                PRAGMA user_version=2;
                CREATE TABLE limits (ceiling INTEGER NOT NULL, token_ceiling INTEGER,
                    cost_reserve INTEGER NOT NULL, token_reserve INTEGER NOT NULL,
                    binding_hash TEXT NOT NULL);
                CREATE TABLE attempts (id TEXT PRIMARY KEY, request_hash TEXT NOT NULL UNIQUE,
                    reserved INTEGER NOT NULL, charged INTEGER, state TEXT NOT NULL,
                    tokens_reserved INTEGER NOT NULL, tokens_charged INTEGER, phase TEXT NOT NULL,
                    request_json TEXT, result_json TEXT);
                CREATE TABLE events (seq INTEGER PRIMARY KEY, attempt_id TEXT NOT NULL, state TEXT NOT NULL,
                    at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')));
            """)
                connection.execute(
                    "INSERT INTO limits VALUES (?,?,?,?,?)",
                    (ceiling, token_ceiling, cost_reserve, token_reserve, binding_hash),
                )
        finally:
            connection.close()
        return cls(path)

    def reserve(
        self,
        attempt_id: str,
        request_hash: str,
        maximum: int,
        *,
        tokens: int = 0,
        phase: str = "work",
        request: dict | None = None,
    ) -> None:
        if (
            not attempt_id
            or not re.fullmatch(r"[0-9a-f]{64}", request_hash)
            or type(maximum) is not int
            or not 0 < maximum <= 2**60
            or type(tokens) is not int
            or not 0 <= tokens <= 2**60
            or phase not in {"work", "verification"}
        ):
            raise Denied("invalid reservation")
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            ceiling, token_ceiling, protected_cost, protected_tokens, binding = connection.execute(
                "SELECT * FROM limits"
            ).fetchone()
            if binding:
                if (
                    not request
                    or request.get("binding_hash") != binding
                    or request.get("phase") != phase
                    or digest(encoded(request)) != request_hash
                ):
                    raise Denied("request differs from frozen run binding")
                if connection.execute(
                    "SELECT 1 FROM attempts WHERE state IN ('pending','dispatched')"
                ).fetchone():
                    raise Denied("pending attempt requires reconciliation; no redispatch")
            if connection.execute("SELECT 1 FROM attempts WHERE id=?", (attempt_id,)).fetchone():
                raise Denied("attempt already recorded; reconcile without redispatch")
            if connection.execute("SELECT 1 FROM attempts WHERE request_hash=?", (request_hash,)).fetchone():
                raise Denied("request already recorded; reconcile without redispatch")
            if connection.execute("SELECT 1 FROM attempts WHERE state='uncertain'").fetchone():
                raise Denied("uncertain attempt requires reconciliation")
            totals = connection.execute(
                "SELECT COALESCE(SUM(COALESCE(charged,reserved)),0), "
                "COALESCE(SUM(COALESCE(tokens_charged,tokens_reserved)),0) FROM attempts"
            ).fetchone()
            work = connection.execute(
                "SELECT COALESCE(SUM(COALESCE(charged,reserved)),0), "
                "COALESCE(SUM(COALESCE(tokens_charged,tokens_reserved)),0) FROM attempts WHERE phase='work'"
            ).fetchone()
            if (
                totals[0] + maximum > ceiling
                or token_ceiling is not None
                and totals[1] + tokens > token_ceiling
                or phase == "work"
                and (
                    work[0] + maximum > ceiling - protected_cost
                    or token_ceiling is not None
                    and work[1] + tokens > token_ceiling - protected_tokens
                )
            ):
                raise BudgetDenied("budget exhausted")
            connection.execute(
                "INSERT INTO attempts VALUES (?,?,?,NULL,'pending',?,NULL,?,?,NULL)",
                (
                    attempt_id,
                    request_hash,
                    maximum,
                    tokens,
                    phase,
                    encoded(request).decode() if request else None,
                ),
            )
            connection.execute("INSERT INTO events (attempt_id,state) VALUES (?,'pending')", (attempt_id,))

    def dispatch(self, attempt_id: str) -> None:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            result = connection.execute(
                "UPDATE attempts SET state='dispatched' WHERE id=? AND state='pending'", (attempt_id,)
            )
            if result.rowcount != 1:
                raise Denied("attempt cannot be dispatched")
            connection.execute("INSERT INTO events (attempt_id,state) VALUES (?,'dispatched')", (attempt_id,))

    def reconcile(
        self, attempt_id: str, charged: int | None, *, tokens: int | None = None, result: dict | None = None
    ) -> None:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT reserved,state,tokens_reserved FROM attempts WHERE id=?", (attempt_id,)
            ).fetchone()
            if not row or row[1] == "settled":
                raise Denied("attempt cannot be reconciled")
            bounded_tokens = connection.execute("SELECT token_ceiling FROM limits").fetchone()[0] is not None
            if charged is not None and (
                type(charged) is not int
                or not 0 <= charged <= row[0]
                or bounded_tokens
                and (type(tokens) is not int or not 0 <= tokens <= row[2])
            ):
                connection.execute("UPDATE attempts SET state='uncertain' WHERE id=?", (attempt_id,))
                connection.execute(
                    "INSERT INTO events (attempt_id,state) VALUES (?,'uncertain')", (attempt_id,)
                )
                connection.commit()
                raise Denied("charge exceeds reservation; stop and investigate")
            connection.execute(
                "UPDATE attempts SET charged=?,tokens_charged=?,state=?,result_json=? WHERE id=?",
                (
                    charged,
                    tokens if charged is not None else None,
                    "uncertain" if charged is None else "settled",
                    encoded(result).decode() if result is not None else None,
                    attempt_id,
                ),
            )
            connection.execute(
                "INSERT INTO events (attempt_id,state) VALUES (?,?)",
                (attempt_id, "uncertain" if charged is None else "settled"),
            )

    def snapshot(self) -> dict:
        """Detached durable accounting receipt, without prompt/response contents."""
        with self._connection() as connection:
            connection.row_factory = sqlite3.Row
            limits = dict(connection.execute("SELECT * FROM limits").fetchone())
            attempts = []
            for row in connection.execute("SELECT * FROM attempts ORDER BY rowid"):
                item = dict(row)
                request, result = item.pop("request_json"), item.pop("result_json")
                item["result_sha256"] = digest(result.encode()) if result is not None else None
                item["request_recorded"] = request is not None
                attempts.append(item)
            return {
                "version": 2,
                "limits": limits,
                "attempts": attempts,
                "events": [dict(row) for row in connection.execute("SELECT * FROM events ORDER BY seq")],
            }


def container_command(*, image: str, input_dir: Path, output_dir: Path, run_id: str) -> list[str]:
    """Pinned offline runtime recipe; no execution, pulls, inherited environment or credentials.

    Input directory must contain ONLY the two admitted files and an operator-reviewed
    runner.py. Runtime attestation and canary execution remain a separate prerequisite.
    """
    if not re.fullmatch(r"[a-z0-9][a-z0-9./:_-]*@sha256:[0-9a-f]{64}", image):
        raise Denied("pinned image required")
    if not re.fullmatch(r"[a-f0-9]{32}", run_id):
        raise Denied("invalid run identity")
    for directory in (input_dir, output_dir):
        directory = Path(directory).absolute()
        if not directory.is_dir() or any(
            p.is_symlink() or p.is_junction() for p in [directory, *directory.parents]
        ):
            raise Denied("runtime mount denied")
        if "," in str(directory):
            raise Denied("runtime mount denied")
    if set(p.name for p in input_dir.iterdir()) != {
        "manuscript.tex",
        "historical_verification_record.txt",
        "runner.py",
    }:
        raise Denied("runtime input set denied")
    if any(not p.is_file() or p.is_symlink() or p.is_junction() for p in input_dir.iterdir()):
        raise Denied("runtime input type denied")
    if any(output_dir.iterdir()) or input_dir.resolve() == output_dir.resolve():
        raise Denied("runtime output must be fresh")
    return [
        "docker",
        "run",
        "--rm",
        "--pull=never",
        "--name",
        f"wb-eval-{run_id}",
        "--network=none",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges:true",
        "--user=65534:65534",
        "--pids-limit=64",
        "--memory=512m",
        "--memory-swap=512m",
        "--cpus=1",
        "--ipc=none",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,nodev,size=64m",
        "--workdir=/tmp",
        "--env",
        "HOME=/tmp",
        "--env",
        "PYTHONDONTWRITEBYTECODE=1",
        "--mount",
        f"type=bind,source={input_dir.resolve()},target=/inputs,readonly",
        "--mount",
        f"type=bind,source={output_dir.resolve()},target=/outputs",
        image,
        "python3",
        "-I",
        "-B",
        "/inputs/runner.py",
    ]
