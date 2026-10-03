"""Preserve a fresh take's natural pauses and produce one uninterrupted video soundtrack."""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import wave
from pathlib import Path

from elevenlabs_narrate import split_take


def duration(path):
    with wave.open(str(path), "rb") as audio:
        return audio.getnframes() / audio.getframerate()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--assets-dir", type=Path, required=True)
    parser.add_argument("--duration", type=float, required=True)
    parser.add_argument("--ffmpeg", required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error("Use a new empty directory")
    source = args.input_dir / "continuous-voice.wav"
    original_duration = duration(source)
    if not original_duration / 2 <= args.duration <= original_duration * 2:
        parser.error("Target duration requires excessive tempo change")
    output.mkdir(parents=True, exist_ok=True)
    tempo = (
        1.0
        if abs(original_duration - args.duration) / args.duration < 0.02
        else original_duration / args.duration
    )
    base = [args.ffmpeg, "-hide_banner", "-nostats", "-nostdin", "-i", str(source)]
    measured = subprocess.run(
        [*base, "-af", f"atempo={tempo},volumedetect", "-f", "null", "NUL"],
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    )
    mean = float(re.search(r"mean_volume: ([-\d.]+) dB", measured.stderr)[1])
    peak = float(re.search(r"max_volume: ([-\d.]+) dB", measured.stderr)[1])
    # One fixed gain cannot pump between sentences. Leave headroom for AAC peaks.
    gain = min(-20 - mean, -2 - peak)
    subprocess.run(
        [
            *base,
            "-af",
            f"atempo={tempo},volume={gain}dB",
            "-ac",
            "1",
            "-ar",
            "22050",
            "-c:a",
            "pcm_s16le",
            str(output / "continuous-voice.wav"),
        ],
        capture_output=True,
        check=True,
        timeout=120,
    )
    actual_duration = duration(output / "continuous-voice.wav")
    scale = actual_duration / original_duration
    alignment = json.loads((args.input_dir / "continuous-alignment.json").read_text(encoding="utf-8"))
    for key in ("character_start_times_seconds", "character_end_times_seconds"):
        alignment[key] = [t * scale for t in alignment[key]]
    (output / "continuous-alignment.json").write_text(json.dumps(alignment), encoding="utf-8")
    for name in ("narration.json", "voice-profile.json"):
        shutil.copy2(args.input_dir / name, output / name)
    chapters = json.loads((output / "narration.json").read_text(encoding="utf-8"))
    split_take(output, chapters)
    shutil.copy2(output / "continuous-voice.wav", output / "master-voice.wav")
    for path in args.assets_dir.iterdir():
        if path.name == "callouts.json" or re.fullmatch(r"cue-\d+\.png", path.name):
            shutil.copy2(path, output / path.name)
    report = {
        "mode": "continuous natural pauses",
        "speed": tempo,
        "sentence_pause": 0,
        "scene_pause": 0,
        "fixed_gain_db": gain,
        "noise_gate": False,
        "adaptive_noise_reduction": False,
        "source_duration": original_duration,
        "target_duration": args.duration,
        "duration_seconds": actual_duration,
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "chapters": [
            {
                "chapter": c["id"],
                "duration_seconds": duration(output / f"{c['id']}-voice.wav"),
                "tempo_duration": duration(output / f"{c['id']}-voice.wav"),
                "reference_duration": duration(output / f"{c['id']}-voice.wav") * tempo,
                "events": [],
            }
            for c in chapters
        ],
    }
    (output / "pacing-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (output / "audio-cleanup.json").write_text(
        json.dumps(
            {
                "mode": "fixed gain only; natural background retained",
                "gain_db": gain,
                "master": "master-voice.wav",
                "sentence_splices": 0,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Continuous master: {actual_duration:.2f}s; tempo {tempo:.4f}; fixed gain {gain:.2f} dB")


if __name__ == "__main__":
    main()
