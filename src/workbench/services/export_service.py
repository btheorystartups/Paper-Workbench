"""Export pipeline (P6): canonical manuscript (DB) → Markdown, LaTeX, HTML, DOCX,
BibTeX, and a provenance manifest with checksums.

Rules:
- The DB is the canonical source; exports are derived artifacts, never edited in place.
- Every exported claim keeps its support state visible ([support: ...] annotations in
  draft formats); export never launders uncertainty.
- The manifest records source access levels, AI-provenance summary, audit findings at
  export time, and sha256 of every emitted file. Export implies nothing was submitted
  or published anywhere.
- PDF is intentionally deferred (WeasyPrint/GTK on Windows); LaTeX output compiles with
  any standard toolchain.
"""

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Claim, ClaimEvidence, Excerpt, ResearchObject, Source
from ..vocab import ObjectKind
from . import audits, authoring, research


def _latex_escape(text: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#",
        "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(ch, ch) for ch in text)


def _bib_key(source: Source) -> str:
    first_author = (source.authors.split(";")[0].split(",")[0].strip() or "anon").lower()
    first_author = re.sub(r"[^a-z0-9]", "", first_author) or "anon"
    return f"{first_author}{source.year or 'nd'}"


def _collect(session: Session, manuscript_id: str):
    manuscript = session.get(ResearchObject, manuscript_id)
    if manuscript is None or manuscript.kind != ObjectKind.MANUSCRIPT:
        raise research.IntegrityError("manuscript not found")
    sections = authoring.manuscript_sections(session, manuscript_id)
    claims: dict[str, Claim] = {}
    sources: dict[str, Source] = {}
    for section in sections:
        for cid in section.body.get("claim_ids", []):
            claim = session.get(Claim, cid)
            if claim is None:
                continue
            claims[cid] = claim
            for ev in session.scalars(
                select(ClaimEvidence).where(ClaimEvidence.claim_id == cid)
            ):
                if ev.excerpt_id:
                    excerpt = session.get(Excerpt, ev.excerpt_id)
                    if excerpt:
                        src = session.get(Source, excerpt.source_id)
                        if src:
                            sources[src.id] = src
    return manuscript, sections, claims, sources


def _claims_block(claim_ids: list[str], claims: dict[str, Claim], sources: dict[str, Source],
                  session: Session, fmt: str) -> list[str]:
    lines = []
    for cid in claim_ids:
        claim = claims.get(cid)
        if claim is None:
            continue
        cites = []
        for ev in session.scalars(select(ClaimEvidence).where(ClaimEvidence.claim_id == cid)):
            if ev.excerpt_id:
                excerpt = session.get(Excerpt, ev.excerpt_id)
                src = sources.get(excerpt.source_id) if excerpt else None
                if src:
                    cites.append((_bib_key(src), excerpt.locator))
        if fmt == "tex":
            cite = " ".join(f"\\cite{{{k}}}" for k, _loc in cites)
            lines.append(f"% [support: {claim.support}]\n{_latex_escape(claim.text)} {cite}".strip())
        else:
            cite = " ".join(f"[@{k}, {loc}]" for k, loc in cites)
            lines.append(f"{claim.text} {cite} *[support: {claim.support}]*".strip())
    return lines


def export_manuscript(
    session: Session, manuscript_id: str, *, formats: list[str] | None = None
) -> dict:
    formats = formats or ["md", "tex", "html", "docx", "bib"]
    manuscript, sections, claims, sources = _collect(session, manuscript_id)
    out_dir = Path(get_settings().data_dir) / "exports" / manuscript_id
    out_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}

    # --- Markdown (canonical draft rendering) ---
    if "md" in formats:
        md = [f"# {manuscript.title}", ""]
        for s in sections:
            md += [f"## {s.title}", ""]
            if s.body.get("text"):
                md += [s.body["text"], ""]
            block = _claims_block(s.body.get("claim_ids", []), claims, sources, session, "md")
            if block:
                md += ["**Claims:**", ""] + [f"- {line}" for line in block] + [""]
        if sources:
            md += ["## References", ""]
            md += [
                f"- `{_bib_key(s)}`: {s.authors} ({s.year or 'n.d.'}). {s.title}. "
                f"{s.venue}. {'doi:' + s.doi if s.doi else ''} [access: {s.access}]"
                for s in sources.values()
            ]
        written["md"] = out_dir / "manuscript.md"
        written["md"].write_text("\n".join(md), encoding="utf-8")

    # --- LaTeX ---
    if "tex" in formats:
        tex = [
            r"\documentclass{article}", r"\usepackage[utf8]{inputenc}", "",
            f"\\title{{{_latex_escape(manuscript.title)}}}",
            r"\begin{document}", r"\maketitle", "",
        ]
        for s in sections:
            tex.append(f"\\section{{{_latex_escape(s.title)}}}")
            if s.body.get("text"):
                tex.append(_latex_escape(s.body["text"]))
            tex += _claims_block(s.body.get("claim_ids", []), claims, sources, session, "tex")
            tex.append("")
        if sources:
            tex += [r"\bibliographystyle{plain}", r"\bibliography{references}"]
        tex.append(r"\end{document}")
        written["tex"] = out_dir / "manuscript.tex"
        written["tex"].write_text("\n".join(tex), encoding="utf-8")

    # --- HTML (deterministic, no external assets) ---
    if "html" in formats:
        import html as _html

        parts = [f"<h1>{_html.escape(manuscript.title)}</h1>"]
        for s in sections:
            parts.append(f"<h2>{_html.escape(s.title)}</h2>")
            if s.body.get("text"):
                parts.append(f"<p>{_html.escape(s.body['text'])}</p>")
            block = _claims_block(s.body.get("claim_ids", []), claims, sources, session, "md")
            if block:
                parts.append("<ul>" + "".join(f"<li>{_html.escape(b)}</li>" for b in block) + "</ul>")
        written["html"] = out_dir / "manuscript.html"
        written["html"].write_text(
            "<!doctype html><meta charset='utf-8'><title>"
            + manuscript.title + "</title>" + "\n".join(parts),
            encoding="utf-8",
        )

    # --- DOCX (python-docx; lazy import) ---
    if "docx" in formats:
        try:
            import docx
        except ImportError:
            docx = None
        if docx is not None:
            document = docx.Document()
            document.add_heading(manuscript.title, level=0)
            for s in sections:
                document.add_heading(s.title, level=1)
                if s.body.get("text"):
                    document.add_paragraph(s.body["text"])
                for line in _claims_block(
                    s.body.get("claim_ids", []), claims, sources, session, "md"
                ):
                    document.add_paragraph(line, style="List Bullet")
            written["docx"] = out_dir / "manuscript.docx"
            document.save(str(written["docx"]))

    # --- BibTeX ---
    if "bib" in formats and sources:
        entries = []
        for s in sources.values():
            authors = " and ".join(a.strip() for a in s.authors.split(";") if a.strip())
            fields = [f"  title = {{{s.title}}}", f"  author = {{{authors}}}"]
            if s.year:
                fields.append(f"  year = {{{s.year}}}")
            if s.venue:
                fields.append(f"  journal = {{{s.venue}}}")
            if s.doi:
                fields.append(f"  doi = {{{s.doi}}}")
            entries.append(f"@article{{{_bib_key(s)},\n" + ",\n".join(fields) + "\n}")
        written["bib"] = out_dir / "references.bib"
        written["bib"].write_text("\n\n".join(entries), encoding="utf-8")

    # --- Provenance manifest ---
    findings = audits.audit_manuscript(session, manuscript_id)
    manifest = {
        "manuscript_id": manuscript_id,
        "title": manuscript.title,
        "exported_at": datetime.now(UTC).isoformat(),
        "exported_by": "paper-workbench 0.1.0 (export != submission/publication)",
        "sections": [s.id for s in sections],
        "claims": {
            cid: {"support": str(c.support), "text": c.text} for cid, c in claims.items()
        },
        "sources": {
            sid: {
                "bib_key": _bib_key(s), "title": s.title, "doi": s.doi,
                "access": str(s.access), "license": s.license,
                "human_verified": s.human_verified,
            }
            for sid, s in sources.items()
        },
        "audit_findings_at_export": findings,
        "files": {},
    }
    for fmt, path in written.items():
        manifest["files"][fmt] = {
            "path": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return {
        "out_dir": str(out_dir),
        "files": {fmt: str(p) for fmt, p in written.items()} | {"manifest": str(manifest_path)},
        "audit_findings": len(findings),
    }
