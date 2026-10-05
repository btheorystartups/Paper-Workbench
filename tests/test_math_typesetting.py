import html
import io
import json
import zipfile

import pytest
from pypdf import PdfReader
from test_research_task_api import client as client

from workbench.services import export_service, math_typesetting, research_results
from workbench.services.research import IntegrityError

MATRIX = r"\[D=\begin{bmatrix}0&0\\1&0\end{bmatrix},\quad x\in\mathbb{R}\]"


def test_math_renders_offline_as_vectors_and_preserves_surrounding_prose():
    output, count = math_typesetting.render_html("<p>Before " + html.escape(MATRIX) + " after</p>")
    assert count == 1
    assert "data:image/svg+xml;base64," in output
    assert output.startswith("<p>Before ") and output.endswith(" after</p>")
    if not export_service.weasyprint_available():
        pytest.skip("SVG verified; optional WeasyPrint PDF runtime is unavailable")
    rendered = research_results.render_sections("Math regression", [("Matrix", MATRIX)])
    assert rendered.math_count == 1
    assert rendered.manifest()["math_renderer"] == "MathJax 3.2.2 SVG"
    assert len(PdfReader(io.BytesIO(rendered.data)).pages) == 1


@pytest.mark.parametrize("command", [r"\href{https://example.com}{x}", r"\input{secret}", r"\require{html}"])
def test_external_commands_rejected(command):
    with pytest.raises(IntegrityError, match="unsupported"):
        math_typesetting.render_html(html.escape(r"\[" + command + r"\]"))


def test_explicit_math_never_silently_uses_text_fallback(monkeypatch):
    monkeypatch.setattr(export_service, "weasyprint_status", lambda: {"available": False})
    with pytest.raises(IntegrityError, match="lose equations"):
        export_service._render_pdf("Math", html.escape(MATRIX), [MATRIX], "auto")


def test_tex_export_preserves_math_but_escapes_prose_and_privacy_keeps_matrix_rows():
    value = "Text & " + MATRIX
    assert math_typesetting.latex_text(value, export_service._latex_escape) == r"Text \& " + MATRIX
    assert research_results.safe_text(MATRIX) == MATRIX
    assert "server" not in research_results.safe_text(r"Private \\server\share\paper.pdf")


def test_unmarked_equations_are_not_guessed_and_invalid_tex_fails():
    text = "Plain x^2 and [[0,0],[1,0]] remain exact."
    assert math_typesetting.render_html(text) == (text, 0)
    with pytest.raises(IntegrityError, match="typesetting failed"):
        math_typesetting.render_html(r"\(\NotARealMacro{x}\)")


def test_math_control_characters_are_removed_inside_tex_spans():
    output, count = math_typesetting.render_html("\\(\x7f\\delta(\\pi r,\x7f\\pi s)\\)")
    assert count == 1
    assert "data:image/svg+xml;base64," in output
    assert "\x7f" not in output


def test_math_task_downloads_use_shared_renderer(client):
    if not export_service.weasyprint_available():
        pytest.skip("Optional WeasyPrint runtime unavailable")
    workspace = client.post("/workspaces", json={"name": "Math fixture"}).json()
    project = client.post("/projects", json={"workspace_id": workspace["id"], "name": "Math"}).json()
    root = f"/projects/{project['id']}/research-tasks"
    task = client.post(root, json={"question": "Inspect this finite table: " + MATRIX}).json()
    response = client.get(root + "/" + task["id"] + "/results.pdf")
    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")
    response = client.get(root + "/" + task["id"] + "/download")
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert json.loads(archive.read("results-rendering.json"))["math_count"] == 1
