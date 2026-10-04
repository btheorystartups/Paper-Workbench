"""Deterministic bibliography completion markers shared by drafts and release audits."""

import re


def bibliography_markers(source, *, bibliography_context=False):
    """Find explicit placeholders; general prose about missing evidence is not classified."""
    if type(source) is not str:
        return []
    hits = {
        match.start(): match.group()
        for match in re.finditer(
            r"\bbibliographic details? to be checked\b|\bcitation needed\b", source, re.I
        )
    }
    regions = [(0, len(source))] if bibliography_context else []
    regions += [
        (match.start(), match.end())
        for match in re.finditer(r"\\begin\{thebibliography\}.*?\\end\{thebibliography\}", source, re.S)
    ]
    headings = list(re.finditer(r"^#{1,6}[ \t]+(.+?)[ \t]*$", source, re.M))
    for index, heading in enumerate(headings):
        if heading.group(1).casefold() in {"references", "bibliography", "works cited"}:
            end = headings[index + 1].start() if index + 1 < len(headings) else len(source)
            regions.append((heading.end(), end))
    for start, end in regions:
        for match in re.finditer(r"\b(?:TODO|TBD)\b", source[start:end], re.I):
            hits[start + match.start()] = match.group()
    return [
        {"line": source.count("\n", 0, offset) + 1, "marker": marker}
        for offset, marker in sorted(hits.items())
    ]
