"""Explicit one-time download of two hash-pinned model assets; never sends research text."""

import argparse
import hashlib
import json
import urllib.request
from pathlib import Path

from workbench.providers.research_embeddings import SPECS, model_directory, model_name


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=model_directory())
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    spec = SPECS[model_name()]
    repository, revision = spec["repository"], spec["revision"]
    for name, (remote, digest) in spec["files"].items():
        path = args.output / name
        if path.exists():
            if path.stat().st_size > 160_000_000 or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError(f"Existing {name} differs; choose a new model directory")
            continue
        url = f"https://huggingface.co/{repository}/resolve/{revision}/{remote}"
        with urllib.request.urlopen(url, timeout=60) as response:
            data = response.read(160_000_001)
        if len(data) > 160_000_000 or hashlib.sha256(data).hexdigest() != digest:
            raise ValueError(f"Download checksum/size failed for {name}")
        with path.open("xb") as stream:
            stream.write(data)
    receipt = args.output / "model-provenance.json"
    if not receipt.exists():
        receipt.write_text(json.dumps({"repository": repository, "revision": revision,
            "license": "Apache-2.0", "model_card": f"https://huggingface.co/{repository}/blob/{revision}/README.md",
            "files": spec["files"], "research_text_sent": False}, indent=2), encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
