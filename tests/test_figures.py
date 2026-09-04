"""Figures/tables: canonical data provenance, real rendering, staleness, captions, export."""

from pathlib import Path

import pytest

from workbench.services import authoring, export_service, figures, research
from workbench.vocab import ObjectKind

mpl = pytest.importorskip("matplotlib")  # render tests skip if the [figures] extra is absent


@pytest.fixture()
def dataset(session, project, tmp_path, monkeypatch):
    monkeypatch.setenv("WB_DATA_DIR", str(tmp_path / "data"))
    from workbench import config

    config.get_settings.cache_clear()
    return figures.create_dataset(
        session, project.id, name="bench",
        columns=["n", "cm_ms", "bitset_ms"],
        rows=[[8, 1.2, 0.6], [12, 2.1, 1.0], [16, 3.4, 1.4]],
    )


def test_dataset_hash_is_canonical(session, project):
    a = figures.create_dataset(session, project.id, name="a", columns=["x"], rows=[[1], [2]])
    b = figures.create_dataset(session, project.id, name="b", columns=["x"], rows=[[1], [2]])
    assert a.body["data_hash"] == b.body["data_hash"]
    assert a.body["n_rows"] == 2
    with pytest.raises(figures.FigureError, match="row must match"):
        figures.create_dataset(session, project.id, name="bad", columns=["x", "y"], rows=[[1]])


def test_render_figure_writes_artifacts_and_provenance(session, project, dataset):
    fig = figures.render_figure(
        session, project.id, title="CM vs bitset", dataset_id=dataset.id,
        spec={"kind": "line", "x": "n", "series": ["cm_ms", "bitset_ms"], "ylabel": "ms"},
    )
    assert fig.kind == ObjectKind.FIGURE
    assert fig.body["number"] == 1
    assert fig.body["colorblind_safe"] is True
    assert fig.body["data_hash"] == dataset.body["data_hash"]
    png = Path(fig.body["png_path"])
    assert png.is_file() and png.read_bytes().startswith(b"\x89PNG")
    assert Path(fig.body["svg_path"]).read_text(encoding="utf-8").lstrip().startswith("<?xml")


def test_render_all_kinds(session, project, dataset):
    for spec in (
        {"kind": "bar", "x": "n", "series": ["cm_ms"]},
        {"kind": "scatter", "x": "n", "series": ["bitset_ms"]},
        {"kind": "scree", "series": ["cm_ms"]},
        {"kind": "heatmap", "row_labels": "n"},
    ):
        fig = figures.render_figure(session, project.id, title=spec["kind"],
                                    dataset_id=dataset.id, spec=spec)
        assert Path(fig.body["png_path"]).is_file()
    with pytest.raises(figures.FigureError, match="spec.kind"):
        figures.render_figure(session, project.id, title="x", dataset_id=dataset.id,
                              spec={"kind": "pie"})


def test_build_table(session, project, dataset):
    tbl = figures.build_table(session, project.id, title="Timings", dataset_id=dataset.id,
                              columns=["n", "cm_ms"])
    assert tbl.kind == ObjectKind.TABLE
    assert "| n | cm_ms |" in tbl.body["markdown"]
    assert tbl.body["data_hash"] == dataset.body["data_hash"]
    assert "n,cm_ms" in tbl.body["csv"]


def test_staleness_detection(session, project, dataset):
    fig = figures.render_figure(session, project.id, title="F", dataset_id=dataset.id,
                                spec={"kind": "bar", "x": "n", "series": ["cm_ms"]})
    # not stale yet
    findings = figures.audit_artifacts(session, project.id)
    assert not any(f["code"] == "artifact-stale" for f in findings)
    # mutate the source dataset → figure becomes stale
    dataset.body = {**dataset.body, "rows": [[8, 9.9, 0.6]],
                    "data_hash": figures.Dataset(dataset.body["columns"], [[8, 9.9, 0.6]]).hash()}
    session.flush()
    stale = figures.audit_artifacts(session, project.id)
    assert any(f["code"] == "artifact-stale" and f["object_id"] == fig.id for f in stale)


def test_orphan_and_no_caption_findings(session, project, dataset):
    fig = figures.render_figure(session, project.id, title="F", dataset_id=dataset.id,
                                spec={"kind": "bar", "x": "n", "series": ["cm_ms"]})
    codes = {f["code"] for f in figures.audit_artifacts(session, project.id)}
    assert "artifact-no-caption" in codes
    # soft-delete the dataset → orphan
    from workbench.models import utcnow

    dataset.deleted_at = utcnow()
    session.flush()
    codes2 = {f["code"] for f in figures.audit_artifacts(session, project.id)}
    assert "artifact-orphan" in codes2


def test_caption_generation_is_review_gated(session, project, dataset):
    fig = figures.render_figure(session, project.id, title="F", dataset_id=dataset.id,
                                spec={"kind": "bar", "x": "n", "series": ["cm_ms"]})
    art = figures.generate_caption(session, fig.id)
    assert art.ai_suggested is True and art.accepted_by_user is False
    assert art.body["caption_human_reviewed"] is False
    # fake provider returns a non-JSON reply → caption falls back to the whole text, alt empty
    assert isinstance(art.body["caption"], str)


def test_export_includes_supplements_with_provenance(session, project, dataset):
    fig = figures.render_figure(session, project.id, title="F", dataset_id=dataset.id,
                                spec={"kind": "bar", "x": "n", "series": ["cm_ms"]})
    tbl = figures.build_table(session, project.id, title="T", dataset_id=dataset.id)
    ms = authoring.create_manuscript(session, project.id, title="M")
    authoring.add_section(session, ms.id, heading="Results", text="see figures")
    result = export_service.export_manuscript(session, ms.id, formats=["md"])
    import json

    manifest = json.loads(Path(result["files"]["manifest"]).read_text(encoding="utf-8"))
    supp = {s["id"]: s for s in manifest["supplements"]}
    assert fig.id in supp and tbl.id in supp
    assert supp[fig.id]["stale"] is False
    assert supp[fig.id]["data_hash"] == dataset.body["data_hash"]
    # the figure PNG was copied into the bundle
    assert (Path(result["out_dir"]) / "supplements" / supp[fig.id]["file"]).is_file()
