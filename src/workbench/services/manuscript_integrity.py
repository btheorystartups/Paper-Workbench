"""Conservative text diagnostics, not mathematical validation or automatic repair."""

import re

POLICY = "manuscript-escaping-integrity-v1"

_MATH = re.compile(r"\\\[(.*?)\\\]|\\\((.*?)\\\)|\$\$(.*?)\$\$|(?<!\\)\$(.+?)(?<!\\)\$", re.S)
_CODE = re.compile(r"(?ms)^ *```.*?^ *```[^\n]*|`[^`\n]*`")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_DAMAGED_GUARD = re.compile(r"(?<=[\w})\]])\r?\n[ \t]*e(?:q)?(?=\\(?:varnothing|emptyset)\b)")
_DAMAGED_COMMAND = re.compile(r"(?<!\r)\r(?!\n)(?:ight|angle|ho)\b|\t(?:ext(?=\{)|imes\b|heta\b)")


def text_issues(text, path, *, section_id=None):
    masked = list(text)
    for match in _CODE.finditer(text):
        masked[match.start():match.end()] = " " * (match.end() - match.start())
    math_text = "".join(masked)
    found = [(m.start(), m.end(), "control_character") for m in _CONTROL.finditer(text)]
    for span in _MATH.finditer(math_text):
        for pattern in (_DAMAGED_GUARD, _DAMAGED_COMMAND):
            found.extend((span.start() + m.start(), span.start() + m.end(), "suspected_math_escape")
                         for m in pattern.finditer(span.group()))
    issues = []
    for start, end, code in sorted(set(found)):
        issues.append({
            "code": code, "path": path, "section_id": section_id,
            "offset": start, "line": text.count("\n", 0, start) + 1,
            "column": start - text.rfind("\n", 0, start),
            "excerpt": repr(text[max(0, start - 24):min(len(text), end + 40)]),
            "message": "Possible escaping damage at this location. Compare the retained raw JSON "
            "and source notation; return an explicit, source-checked correction. Do not globally "
            "decode backslashes, replace newlines, or infer a new mathematical hypothesis.",
        })
    return issues


def candidate_issues(candidate):
    issues = text_issues(candidate.get("title", ""), "/title")
    for index, section in enumerate(candidate.get("sections", [])):
        for field in ("heading", "text"):
            issues.extend(text_issues(section.get(field, ""), f"/sections/{index}/{field}",
                                      section_id=section.get("id")))
    for index, claim in enumerate(candidate.get("claims", [])):
        issues.extend(text_issues(claim.get("statement", ""), f"/claims/{index}/statement"))
    for index, text in enumerate(candidate.get("limitations", [])):
        issues.extend(text_issues(text, f"/limitations/{index}"))
    return issues


def report(candidate):
    issues = candidate_issues(candidate)
    return {"policy": POLICY, "status": "needs_review" if issues else "no_suspect_patterns_detected",
            "issues": issues, "automatic_repairs": False,
            "notice": "Heuristic escaping diagnostics only; a clean result does not certify "
            "equation meaning, rendering, or proof correctness."}
