"""Check guided render frames, timing, and inserted silence; save a visual contact sheet."""

import argparse
import hashlib
import json
import subprocess
import wave
from pathlib import Path


def main():
    from PIL import Image, ImageDraw

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--ffmpeg", required=True)
    args = parser.parse_args()
    root = args.input_dir.resolve()
    report = json.loads((root / "render-verification.json").read_text(encoding="utf-8"))
    pacing = json.loads((root / "pacing-report.json").read_text(encoding="utf-8"))
    output = root / "verification"
    output.mkdir(exist_ok=True)
    checks = []
    for index, cue in enumerate(report["callouts"]):
        image_path = output / f"highlight-{index:02}.png"
        subprocess.run(
            [
                args.ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
                "-y",
                "-ss",
                str((cue["start"] + cue["end"]) / 2),
                "-i",
                str(root / f"{cue['chapter']}-final.mp4"),
                "-frames:v",
                "1",
                str(image_path),
            ],
            capture_output=True,
            check=True,
            timeout=30,
        )
        with Image.open(image_path) as image:
            x, y, width, height = cue["box"]
            left, top = round(40 + x * 1.15 - 5), round(84 + y * 1.15 - 5)
            right = round(left + width * 1.15 + 10)
            pixels = image.convert("RGB").crop((left, top, right, top + 4))
            raw = pixels.tobytes()
            gold = sum(
                r > 160 and 110 < g < 225 and b < 150 and r > g
                for r, g, b in zip(raw[0::3], raw[1::3], raw[2::3], strict=True)
            )
            if gold < width:
                raise ValueError(f"Missing rendered outline for {cue['label']}")
        checks.append({"chapter": cue["chapter"], "label": cue["label"], "gold_pixels": gold})
    pause_count = 0
    combined = bytearray()
    for chapter in pacing["chapters"]:
        with wave.open(str(root / f"{chapter['chapter']}-voice.wav"), "rb") as audio:
            rate = audio.getframerate()
            pcm = audio.readframes(audio.getnframes())
        combined.extend(pcm)
        for event in chapter["events"]:
            lo, hi = (round(event[key] * rate) for key in ("pause_start_seconds", "pause_end_seconds"))
            if any(pcm[lo * 2 : hi * 2]):
                raise ValueError("Inserted pause contains nonzero samples")
            pause_count += 1
        target = chapter["reference_duration"] / pacing["speed"]
        if abs(chapter["tempo_duration"] - target) > 0.05:
            raise ValueError("Chapter pace differs from reference target")
    if (root / "master-voice.wav").exists():
        with wave.open(str(root / "master-voice.wav"), "rb") as audio:
            master = audio.readframes(audio.getnframes())
        if combined != master:
            raise ValueError("Chapter audio differs from uninterrupted master")
    sheet = Image.new("RGB", (1600, ((len(checks) + 3) // 4) * 250), "#101f31")
    draw = ImageDraw.Draw(sheet)
    for index, check in enumerate(checks):
        x, y = index % 4 * 400, index // 4 * 250
        with Image.open(output / f"highlight-{index:02}.png") as frame:
            sheet.paste(frame.resize((400, 225)), (x, y))
        draw.text((x + 4, y + 229), f"{index}: {check['label']}", fill="white")
    sheet.save(output / "highlight-contact-sheet.jpg")
    final = root / "Paper-Workbench-Walkthrough.mp4"
    result = {
        "rendered_callouts": checks,
        "silent_pauses": pause_count,
        "sha256": hashlib.sha256(final.read_bytes()).hexdigest(),
        "bytes": final.stat().st_size,
    }
    (output / "checks.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Verified {len(checks)} rendered outlines and {pause_count} silent pauses.", flush=True)
    print(json.dumps({k: v for k, v in result.items() if k != "rendered_callouts"}))


if __name__ == "__main__":
    main()
