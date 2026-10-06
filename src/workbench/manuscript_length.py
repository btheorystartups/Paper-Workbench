"""Pure section-text measurement shared by author prechecks and final admission."""

from pydantic import Field, model_validator

from .models import stable_hash
from .research_contract import ContractModel, Key, Text

TOOL_NAME = "check_manuscript_length"
TOOL_NAMESPACE = "paper_counter"
MAX_CHECKS = 4


class LengthSection(ContractModel):
    id: Key
    text: Text


class LengthInput(ContractModel):
    sections: list[LengthSection] = Field(min_length=1, max_length=24)

    @model_validator(mode="after")
    def unique_ids(self):
        if len({s.id for s in self.sections}) != len(self.sections):
            raise ValueError("section IDs must be unique")
        return self


def measure(sections, bounds):
    # Legacy graph measurements provide text only; author-tool inputs require IDs.
    texts = [{"id": section.get("id", str(index)), "text": section["text"].strip()}
             for index, section in enumerate(sections)]
    counts = [{"id": section["id"], "word_count": len(section["text"].split())} for section in texts]
    count = sum(section["word_count"] for section in counts)
    within = bounds is None or bounds["min_words"] <= count <= bounds["max_words"]
    return {
        "counting_policy": "section-text-whitespace-v1",
        "word_count": count,
        "section_counts": counts,
        "section_text_sha256": stable_hash(texts),
        "bounds": bounds,
        "target_words": (bounds["min_words"] + bounds["max_words"]) // 2 if bounds else None,
        "status": "not_requested" if bounds is None else ("within_bounds" if within else "out_of_bounds"),
    }


def tool_spec():
    return {
        "type": "function",
        "name": TOOL_NAME,
        "deferLoading": False,
        "description": "Count all manuscript section text before final JSON. Returns "
        "exact whitespace word counts, inclusive bounds and a content "
        "hash. No files or code execution. At most four calls per author turn.",
        "inputSchema": LengthInput.model_json_schema(),
    }


def namespaced_tool_spec():
    return {
        "type": "namespace",
        "name": TOOL_NAMESPACE,
        "description": "In-memory manuscript length measurement only.",
        "tools": [tool_spec()],
    }
