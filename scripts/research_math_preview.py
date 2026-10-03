"""Typeset the bounded narrow acceptance examples; preserve the original reports."""

import argparse
import hashlib
import io
import json
import zipfile
from pathlib import Path

from workbench.services import research_results
from workbench.services.publication_packages import checksummed_zip


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--previous-package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    original = args.input.read_bytes()
    expected = "62bbb8b55aed9a583ddf2f64031c6bfe901d2d4209b2f224244a89d02e6603d0"
    if hashlib.sha256(original).hexdigest() != expected:
        raise ValueError("This presentation applies only to the frozen narrow acceptance run")
    args.output.mkdir(parents=True, exist_ok=False)
    snapshot = research_results.snapshot_from_package(original)
    presentation = [
        (
            "Typeset finite examples - presentation only",
            "The following equations restate the two explicit tables recomputed in package version 2. "
            "They use the chosen parameters \\(\\varepsilon=1\\) and \\(q=2\\). "
            "No original report, claim scope, or human review has changed.",
        ),
        (
            "Source-described minimal example: one coarse cell",
            r"For the two refined states, the recorded directed distance table is"
            "\n\n" + r"\[D_0=\begin{bmatrix}0&0\\1&0\end{bmatrix}.\]"
            "\n\n" + r"Using strict forward balls \(B_D(x,r)=\{y:D(x,y)<r\}\), the open sets are"
            "\n\n" + r"\[\mathcal{T}_0=\{\varnothing,\{1\},\{0,1\}\}.\]"
            "\n\nBoth states map to the same coarse cell. There are no cross-cell pairs to test.",
        ),
        (
            "Conditional four-state specialization - not source-stated",
            r"In the order \((c_0,c_1,d_0,d_1)\), the recomputed conditional table is"
            "\n\n" + r"\[D_1=\begin{bmatrix}0&0&2&2\\1&0&2&2\\2&2&0&0\\2&2&1&0\end{bmatrix}.\]"
            "\n\n" + r"All eight ordered cross-cell pairs have distance \(q=2\). The nine open sets are"
            "\n\n" + r"\[\begin{aligned}\mathcal{T}_1=\{&\varnothing,\{c_1\},\{c_0,c_1\},"
            r"\{d_1\},\{d_0,d_1\},\{c_1,d_1\},\\"
            r"&\{c_0,c_1,d_1\},\{c_1,d_0,d_1\},\{c_0,c_1,d_0,d_1\}\}.\end{aligned}\]"
            "\n\n" + r"Both tables satisfy \(D(x,z)\leq\max\{D(x,y),D(y,z)\}\) "
            "for every triple in those finite instances. "
            "This is not a proof of the general claim or novelty.",
        ),
    ]
    rendered = research_results.render_sections(
        "Delegated research results - typeset mathematics",
        presentation + research_results.report_sections(snapshot),
    )
    (args.output / "results-math.pdf").write_bytes(rendered.data)
    previous = args.previous_package.read_bytes()
    with zipfile.ZipFile(io.BytesIO(previous)) as archive:
        if archive.testzip() is not None:
            raise ValueError("Previous package CRC failure")
        metadata = json.loads(archive.read("package-manifest.json"))
        for name, entry in metadata["files"].items():
            if hashlib.sha256(archive.read(name)).hexdigest() != entry["sha256"]:
                raise ValueError("Previous package hash mismatch")
        files = {name: archive.read(name) for name in metadata["files"]}
    if files["tasks/task-001/PRIVATE-original-research-task.zip"] != original:
        raise ValueError("Previous package refers to a different research input")
    files["tasks/task-001/research-results.pdf"] = rendered.data
    files["math-presentation.json"] = json.dumps(presentation, indent=2).encode()
    files["math-rendering.json"] = json.dumps(rendered.manifest(), indent=2).encode()
    previous_hash = hashlib.sha256(previous).hexdigest()
    basis = hashlib.sha256((metadata["snapshot_version"] + json.dumps(presentation)).encode()).hexdigest()
    history = json.loads(files["history.json"])
    history.update(
        package_version=3,
        snapshot_version=basis,
        previous_version={"package_version": 2, "zip_sha256": previous_hash},
    )
    history["events"].append({"action": "typeset_finite_example_presentation", "approval_changed": False})
    files["history.json"] = json.dumps(history, indent=2).encode()
    files["README_FIRST.md"] += (
        b"\nVersion 3 adds typeset finite-example presentation. Original reports remain exact.\n"
    )
    metadata.pop("files")
    metadata.update(package_version=3, snapshot_version=basis, previous_package_sha256=previous_hash)
    metadata["renderers"]["tasks/task-001/research-results.pdf"] = rendered.manifest()
    bundle = checksummed_zip(files, metadata)
    (args.output / "research-artifacts-v3.zip").write_bytes(bundle)
    print(json.dumps({"renderer": rendered.manifest(), "package_sha256": hashlib.sha256(bundle).hexdigest()}))


if __name__ == "__main__":
    main()
