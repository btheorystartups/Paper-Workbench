"""Clean and normalize a continuous narration once, then split at aligned chapter gaps."""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

from elevenlabs_narrate import split_take


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--assets-dir", type=Path, required=True)
    parser.add_argument("--ffmpeg", required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error("Use a new empty directory to preserve original audio")
    output.mkdir(parents=True, exist_ok=True)
    source = args.input_dir / "continuous-voice.wav"
    filters = (
        "highpass=f=70,afftdn=nr=12:nf=-45:tn=1,"
        "agate=threshold=0.006:ratio=3:attack=10:release=120:range=0.02"
    )
    base = [args.ffmpeg, "-hide_banner", "-nostats", "-nostdin", "-i", str(source)]
    measured = subprocess.run(
        [*base, "-af", filters + ",loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json", "-f", "null", "NUL"],
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    )
    stats = json.loads(re.search(r'\{\s*"input_i".*?\}', measured.stderr, re.S)[0])
    normalization = (
        "loudnorm=I=-16:TP=-1.5:LRA=11:linear=true:"
        f"measured_I={stats['input_i']}:measured_TP={stats['input_tp']}:"
        f"measured_LRA={stats['input_lra']}:measured_thresh={stats['input_thresh']}:"
        f"offset={stats['target_offset']}"
    )
    subprocess.run(
        [
            *base,
            "-af",
            filters + "," + normalization,
            "-ar",
            "22050",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(output / "continuous-voice.wav"),
        ],
        capture_output=True,
        check=True,
        timeout=120,
    )
    for name in ("narration.json", "voice-profile.json", "continuous-alignment.json"):
        shutil.copy2(args.input_dir / name, output / name)
    chapters = json.loads((output / "narration.json").read_text(encoding="utf-8"))
    split_take(output, chapters)
    for path in args.assets_dir.iterdir():
        if path.suffix in {".png", ".webm"}:
            shutil.copy2(path, output / path.name)
    report = {
        "filters": filters,
        "normalization": normalization,
        "measurement": stats,
        "scope": "one continuous take; no per-chapter loudness adjustment",
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    }
    (output / "audio-cleanup.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("Cleaned and normalized one continuous take; split all chapters.", flush=True)


if __name__ == "__main__":
    main()
