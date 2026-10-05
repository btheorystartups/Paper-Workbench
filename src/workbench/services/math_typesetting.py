"""Offline, bounded mathematical typesetting for already-escaped HTML.

Only delimited TeX is parsed. Plain prose is never guessed to be an equation.
MathJax converts math to self-contained SVG paths; browser JavaScript is not used.
"""

import base64
import html
import json
import re
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path
from xml.etree import ElementTree

from .research import IntegrityError

MATH = re.compile(r"\\\[(.*?)\\\]|\\\((.*?)\\\)|\$\$(.*?)\$\$|(?<!\\)\$([^$\n]+?)\$", re.S)
FORBIDDEN = re.compile(
    r"\\(?:require|href|url|includegraphics|style|class|cssId|htmlClass|htmlId|htmlStyle|htmlData|"
    r"input|include|write|read|openin|openout|catcode|def|gdef|edef|xdef|let|csname|newcommand)\b"
)
CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
SVG_TAGS = {"svg", "g", "path", "rect", "line", "polygon", "polyline", "circle", "ellipse", "title"}


@lru_cache(maxsize=256)
def _svg_batch(encoded: str) -> tuple[str, ...]:
    node = shutil.which("node")
    script = Path(__file__).resolve().parents[1] / "math_runtime" / "render.cjs"
    if not node or not (script.parent / "node_modules/mathjax-full/package.json").is_file():
        raise IntegrityError("Math PDF requires Node.js and npm ci in src/workbench/math_runtime.")
    try:
        completed = subprocess.run(
            [node, str(script)],
            input=encoded,
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=30,
            cwd=script.parent,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise IntegrityError(
            "Math renderer unavailable or timed out; no plain-text PDF substituted."
        ) from exc
    if completed.returncode or len(completed.stdout) > 16_000_000:
        raise IntegrityError("Math typesetting failed; check equation syntax and supported commands.")
    try:
        values = json.loads(completed.stdout)
        for svg in values:
            root = ElementTree.fromstring(svg)
            for element in root.iter():
                if element.tag.split("}")[-1] not in SVG_TAGS:
                    raise ValueError("unexpected SVG element")
                for key, value in element.attrib.items():
                    if key.lower().startswith("on") or "href" in key or "url(" in value.lower():
                        raise ValueError("active SVG attribute")
        return tuple(values)
    except (ValueError, TypeError, ElementTree.ParseError) as exc:
        raise IntegrityError("Math renderer returned invalid vector output.") from exc


def render_html(document: str) -> tuple[str, int]:
    matches = list(MATH.finditer(document))
    if not matches:
        return document, 0
    if len(matches) > 500:
        raise IntegrityError("At most 500 equations can be typeset per PDF.")
    formulas = []
    for match in matches:
        tex = html.unescape(next(value for value in match.groups() if value is not None))
        # Existing prose renderers insert line-break tags; math receives whitespace instead.
        tex = tex.replace("<br>", "\n").replace("<br/>", "\n")
        tex = CONTROL_CHARS.sub("", tex)
        if len(tex) > 20000 or FORBIDDEN.search(tex):
            raise IntegrityError("Equation contains unsupported markup or commands.")
        formulas.append({"tex": tex, "display": match.group(1) is not None or match.group(3) is not None})
    svgs = _svg_batch(json.dumps(formulas))
    if len(svgs) != len(matches):
        raise IntegrityError("Math renderer omitted an equation.")
    result, offset = [], 0
    for match, formula, svg in zip(matches, formulas, svgs, strict=True):
        result.append(document[offset : match.start()])
        encoded = base64.b64encode(svg.encode()).decode()
        display = (
            "display:block;margin:1em auto;max-width:100%" if formula["display"] else "vertical-align:middle"
        )
        result.append(
            f'<img alt="{html.escape(formula["tex"], quote=True)}" '
            f'style="{display}" src="data:image/svg+xml;base64,{encoded}">'
        )
        offset = match.end()
    result.append(document[offset:])
    return "".join(result), len(matches)


def latex_text(text: str, escape) -> str:
    """Keep only validated math spans; escape all surrounding prose as before."""
    result, offset = [], 0
    for match in MATH.finditer(text):
        tex = next(value for value in match.groups() if value is not None)
        tex = CONTROL_CHARS.sub("", tex)
        if FORBIDDEN.search(tex) or len(tex) > 20000:
            raise IntegrityError("Equation contains unsupported markup or commands.")
        display = match.group(1) is not None or match.group(3) is not None
        _svg_batch(json.dumps([{"tex": tex, "display": display}]))
        result.append(escape(text[offset : match.start()]))
        result.append((r"\[" if display else r"\(") + tex + (r"\]" if display else r"\)"))
        offset = match.end()
    result.append(escape(text[offset:]))
    return "".join(result)
