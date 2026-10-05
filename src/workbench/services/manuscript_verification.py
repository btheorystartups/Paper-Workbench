"""Reviewed deterministic checks. Never imports or executes supplied/generated scripts."""

import hashlib
import itertools
import json
import platform
import threading
import time
from datetime import UTC, datetime
from pathlib import Path


def utcnow():
    return datetime.now(UTC)


def stable_hash(payload):
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def partitions(size):
    result = [()]
    for point in range(size):
        result = [p[:i] + (p[i] + (point,),) + p[i + 1 :] for p in result for i in range(len(p))] + [
            p + ((point,),) for p in result
        ]
    return result


def functions(partition, size):
    return {
        bits
        for bits in itertools.product((0, 1), repeat=size)
        if all(len({bits[x] for x in block}) == 1 for block in partition)
    }


def refines(left, right):
    return all(any(set(a) <= set(b) for b in right) for a in left)


def join(left, right, size):
    groups = [{i} for i in range(size)]
    for block in (*left, *right):
        touched = [g for g in groups if g.intersection(block)]
        groups = [g for g in groups if g not in touched] + [set().union(*touched)]
    return tuple(tuple(sorted(g)) for g in groups)


def execute_routine(name, *, deadline, cancel):
    if name != "finite_partitions_v1":
        raise ValueError("verification routine is not allowlisted")
    started = utcnow().isoformat()
    cases = []
    for size in range(1, 6):
        rows = partitions(size)
        spaces = {p: functions(p, size) for p in rows}
        for left, right in itertools.product(rows, repeat=2):
            if cancel.is_set() or time.monotonic() >= deadline:
                raise ValueError("verification interrupted before completion")
            if (
                (spaces[left] <= spaces[right]) != refines(right, left)
                or len(spaces[left]) != 2 ** len(left)
                or spaces[left] & spaces[right] != functions(join(left, right, size), size)
            ):
                raise ValueError("finite-partition regression failed")
        cases.append({"carrier_size": size, "partitions": len(rows), "ordered_pairs": len(rows) ** 2})
    counterexample = {"P": [[0, 1], [2, 3]], "Q": [[0, 2], [1, 3]], "vector": [0, 0, 1, 1]}
    witness = tuple(counterexample["vector"])
    if (witness not in functions(counterexample["P"], 4)
            or witness in functions(counterexample["Q"], 4)):
        raise ValueError("historical false-generalization witness failed")
    payload = {
        "id": name,
        "routine": name,
        "outcome": "passed_within_scope",
        "executed_by": "workbench_allowlisted_routine",
        "started_at": started,
        "finished_at": utcnow().isoformat(),
        "python": platform.python_version(),
        "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "input": {"carrier_sizes": [1, 2, 3, 4, 5], "codomain": [0, 1]},
        "scope": "Exhaustive finite checking only; not a general proof or novelty assessment.",
        "cases": cases,
        "ordered_pairs": sum(r["ordered_pairs"] for r in cases),
        "checked": [
            "refinement iff reversed inclusion",
            "cardinality 2^blocks",
            "function-space intersection equals space of join/coarsening",
        ],
        "false_generalization_counterexample": counterexample,
    }
    return {**payload, "receipt_sha256": stable_hash(payload)}


VOLATILE_FIELDS = {"started_at", "finished_at", "python", "receipt_sha256"}


def deterministic_result(receipt):
    """Scientific output for comparison; execution timestamps remain in the receipt."""
    return {k: v for k, v in receipt.items() if k not in VOLATILE_FIELDS}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-sha256", required=True)
    args = parser.parse_args()
    actual = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    if args.expected_sha256 != actual:
        parser.error("reviewed implementation hash mismatch; no verification executed")
    receipt = execute_routine(
        "finite_partitions_v1", deadline=time.monotonic() + 30, cancel=threading.Event()
    )
    print(json.dumps(deterministic_result(receipt), sort_keys=True, indent=2))
