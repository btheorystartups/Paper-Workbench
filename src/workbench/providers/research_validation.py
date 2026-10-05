"""Bounded validation codes and schema paths; never retain response text or error messages."""

import json
from functools import cache

from pydantic_core import ErrorType

from workbench.research_contract import OPERATION_MODELS

MAX_ERRORS = 20
CUSTOM_CODES = frozenset({
    "citation_target", "citation_url", "report_duplicate_ids", "report_missing_evidence",
    "report_unverified_result", "report_uncited_prior_art", "report_unrecorded_search",
})
ERROR_CODES = frozenset(ErrorType.__args__) | CUSTOM_CODES


@cache
def schema_fields():
    fields = set()

    def visit(value):
        if isinstance(value, dict):
            fields.update(value.get("properties", {}))
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    for model in OPERATION_MODELS.values():
        visit(model.model_json_schema())
    return frozenset(fields)


def normalize_validation_diagnostics(value):
    """Revalidate worker telemetry at the controller boundary, dropping all free text."""
    if not isinstance(value, dict):
        return None
    count, errors = value.get("error_count"), value.get("errors")
    if type(count) is not int or not 1 <= count <= 1000000 or not isinstance(errors, list) or not errors:
        return None
    clean = []
    for error in errors[:MAX_ERRORS]:
        if not isinstance(error, dict):
            continue
        code = error.get("code")
        if not isinstance(code, str) or code not in ERROR_CODES:
            code = "value_error"
        path = error.get("path", [])
        path = path[:12] if isinstance(path, (list, tuple)) else []
        clean.append({"code": code, "path": [
            item if ((type(item) is int and 0 <= item <= 1000000)
                     or (isinstance(item, str) and item in schema_fields())) else "*"
            for item in path
        ]})
    return {"error_count": count, "errors": clean} if clean else None


def validation_diagnostics(exc):
    if isinstance(exc, json.JSONDecodeError):
        return {"error_count": 1, "errors": [{"code": "json_invalid", "path": []}]}
    errors = exc.errors(include_url=False, include_context=False, include_input=False)
    return normalize_validation_diagnostics({
        "error_count": exc.error_count(),
        "errors": [{"code": error["type"], "path": error["loc"]}
                   for error in errors[:MAX_ERRORS]],
    })
