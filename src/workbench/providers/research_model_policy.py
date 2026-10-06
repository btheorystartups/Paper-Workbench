"""Operator-owned per-role model choices; no model-authored routing or fallback."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints, TypeAdapter

ModelName = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9.-]{0,79}$")]
Role = Literal["proof_method", "source_citation", "literature_contribution", "adversarial",
               "literature_discovery"]


class ModelSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: ModelName
    reasoning_effort: Literal["low", "medium", "high", "xhigh", "max"]


POLICY = TypeAdapter(dict[Role, ModelSelection])


def default_role_policy():
    return {
        role: {"model": "gpt-6-astra", "reasoning_effort": effort}
        for role, effort in {
            "proof_method": "xhigh", "source_citation": "high",
            "literature_contribution": "high", "adversarial": "xhigh",
            "literature_discovery": "high",
        }.items()
    }


def role_selection(role, policy, *, model, effort):
    validated = POLICY.validate_python(policy)
    if set(validated) != set(default_role_policy()):
        raise ValueError("operator model policy must specify every required research role")
    if role in default_role_policy():
        return validated[role].model_dump()
    if role not in {"author", "research"}:
        raise ValueError("unknown research worker role")
    return ModelSelection(model=model, reasoning_effort=effort).model_dump()
