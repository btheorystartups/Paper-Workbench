"""Pure measurement, with synthetic text and no model or filesystem tools."""

import pytest
from pydantic import ValidationError

from workbench.manuscript_length import LengthInput, measure
from workbench.services.manuscript_quality import length_check


def test_counter_and_final_gate_share_counts_and_normalized_binding():
    sections = [{"id": "proof", "text": "  Let x = y.\nThus \\( x \\).  "},
                {"id": "references", "text": "Author\tTitle"}]
    bounds = {"min_words": 10, "max_words": 10}
    result = measure(sections, bounds)
    final = length_check({"title": "Excluded title", "sections": sections}, bounds)
    assert final == {key: result[key] for key in final}
    assert result["word_count"] == 10 and result["status"] == "within_bounds"
    assert [s["word_count"] for s in result["section_counts"]] == [8, 2]
    normalized = LengthInput.model_validate({"sections": sections}).model_dump()["sections"]
    assert measure(normalized, bounds)["section_text_sha256"] == result["section_text_sha256"]
    normalized[0]["text"] += " More"
    assert measure(normalized, bounds)["section_text_sha256"] != result["section_text_sha256"]
    assert "Author" not in str(result)


@pytest.mark.parametrize("sections", [[], [{"id": "x", "text": ""}],
    [{"id": "x", "text": "a"}, {"id": "x", "text": "b"}],
    [{"id": "x", "text": "a", "path": "C:/private"}],
    [{"id": "x", "text": "a" * 24001}], [{"id": str(i), "text": "a"} for i in range(25)]])
def test_counter_input_is_bounded_text_only(sections):
    with pytest.raises(ValidationError):
        LengthInput.model_validate({"sections": sections})


def test_code_looking_text_is_only_counted():
    sections = LengthInput.model_validate({"sections": [{"id": "data", "text": "Remove-Item C:/private; $(Get-Content secret)"}]}).model_dump()["sections"]
    assert measure(sections, None)["word_count"] == 4
