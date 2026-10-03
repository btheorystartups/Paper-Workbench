"""Retime existing narration and add sentence/scene pauses without service calls."""

import argparse
import array
import bisect
import hashlib
import json
import re
import shutil
import subprocess
import wave
from pathlib import Path


def sentence_ends(text):
    # A period inside a decimal or filename is not a sentence boundary.
    return [m.end() for m in re.finditer(r"""[.!?]+["'’”\)\]]*(?=\s|$)""", text)]


def add_pauses(pcm, rate, alignment, scale, sentence_pause, scene_pause, scene_ends):
    text = "".join(alignment["characters"])
    frames = len(pcm) // 2
    ends = sentence_ends(text)
    events = []
    for number, end in enumerate(ends, 1):
        after = end
        while after < len(text) and text[after].isspace():
            after += 1
        if after == len(text):
            cut = frames
        else:
            left = alignment["character_end_times_seconds"][end - 1] * scale
            right = alignment["character_start_times_seconds"][after] * scale
            cut = round(max(left, (left + right) / 2) * rate)
            cut = min(frames, max(0, cut))
        count = round((sentence_pause + (scene_pause if number in scene_ends else 0)) * rate)
        if events and cut < events[-1]["cut_frame"]:
            raise ValueError("Sentence timing is out of order")
        events.append(
            {
                "sentence": number,
                "cut_frame": cut,
                "insert_frames": count,
                "scene_change": number in scene_ends,
            }
        )
    # Five-millisecond fades avoid waveform discontinuities when silence is inserted.
    # No samples are removed, so all alignment and scene timings stay unchanged.
    samples = array.array("h", pcm)
    ramp = max(2, round(rate * 0.005))
    for event in events:
        if not event["insert_frames"]:
            continue
        cut = event["cut_frame"]
        before, after = min(ramp, cut), min(ramp, frames - cut)
        for i in range(before):
            samples[cut - before + i] = round(
                samples[cut - before + i] * (before - 1 - i) / max(1, before - 1)
            )
        for i in range(after):
            samples[cut + i] = round(samples[cut + i] * i / max(1, after - 1))
    pcm = samples.tobytes()
    output = bytearray()
    cursor = 0
    inserted = 0
    for event in events:
        cut = event["cut_frame"]
        output.extend(pcm[cursor * 2 : cut * 2])
        event["pause_start_seconds"] = (cut + inserted) / rate
        output.extend(b"\0" * (event["insert_frames"] * 2))
        inserted += event["insert_frames"]
        event["pause_end_seconds"] = (cut + inserted) / rate
        cursor = cut
    output.extend(pcm[cursor * 2 :])
    cuts = [e["cut_frame"] for e in events]
    cumulative = [0]
    for event in events:
        cumulative.append(cumulative[-1] + event["insert_frames"])

    def retime(value, ending=False):
        frame = min(frames, max(0, round(value * scale * rate)))
        # A character ending on a cut belongs before the pause; a starting one after it.
        slot = bisect.bisect_left(cuts, frame) if ending else bisect.bisect_right(cuts, frame)
        return (frame + cumulative[slot]) / rate

    updated = {
        "characters": alignment["characters"],
        "character_start_times_seconds": [retime(t) for t in alignment["character_start_times_seconds"]],
        "character_end_times_seconds": [retime(t, True) for t in alignment["character_end_times_seconds"]],
    }
    # Punctuation/space tokens may have zero duration on a cut; keep such tokens valid.
    updated["character_end_times_seconds"] = [
        max(start, end)
        for start, end in zip(
            updated["character_start_times_seconds"], updated["character_end_times_seconds"], strict=True
        )
    ]
    return bytes(output), updated, events


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--ffmpeg", required=True)
    parser.add_argument("--speed", type=float, default=0.9)
    parser.add_argument(
        "--reference-dir", type=Path, help="Match each chapter to this original take at --speed."
    )
    parser.add_argument("--sentence-pause", type=float, default=0.25)
    parser.add_argument("--scene-pause", type=float, default=0.1)
    args = parser.parse_args()
    source, output = args.input_dir.resolve(), args.output_dir.resolve()
    if source == output or (output.exists() and any(output.iterdir())):
        parser.error("Use a new, empty output directory; original audio must be preserved.")
    if not 0.5 <= args.speed <= 2 or not 0 <= args.sentence_pause <= 3 or not 0 <= args.scene_pause <= 3:
        parser.error("Speed must be 0.5–2 and pauses 0–3 seconds.")
    output.mkdir(parents=True, exist_ok=True)
    chapters = json.loads((source / "narration.json").read_text(encoding="utf-8"))
    for name in ["narration.json", "voice-profile.json", "capture-verification.json", "audio-cleanup.json"]:
        if (source / name).exists():
            shutil.copy2(source / name, output / name)
    for chapter in chapters:
        for ext in (".webm", ".png"):
            name = chapter["id"] + ext
            if (source / name).exists():
                shutil.copy2(source / name, output / name)
    for name in ("12-literature.png", "12-compute.png", "12-figures.png"):
        shutil.copy2(source / name, output / name)
    report = {
        "speed": args.speed,
        "sentence_pause": args.sentence_pause,
        "scene_pause": args.scene_pause,
        "pitch_preserved": True,
        "pause_edge_fade_ms": 5,
        "external_requests": 0,
        "chapters": [],
    }
    for index, chapter in enumerate(chapters):
        name = chapter["id"]
        audio_path = source / f"{name}-voice.wav"
        timing = json.loads((source / f"{name}-alignment.json").read_text(encoding="utf-8"))
        text = " ".join(chapter["speech"])
        if "".join(timing["characters"]) != text:
            raise ValueError(f"{name}: narration and alignment differ")
        with wave.open(str(audio_path), "rb") as w:
            original_duration = w.getnframes() / w.getframerate()
        reference_duration = original_duration
        if args.reference_dir:
            with wave.open(str(args.reference_dir / f"{name}-voice.wav"), "rb") as w:
                reference_duration = w.getnframes() / w.getframerate()
        tempo = args.speed * original_duration / reference_duration
        slowed = output / f"{name}-tempo.wav"
        subprocess.run(
            [
                args.ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
                "-i",
                str(audio_path),
                "-af",
                f"atempo={tempo}",
                "-ac",
                "1",
                "-c:a",
                "pcm_s16le",
                str(slowed),
            ],
            check=True,
            timeout=60,
        )
        with wave.open(str(slowed), "rb") as w:
            rate, frames = w.getframerate(), w.getnframes()
            pcm = w.readframes(frames)
        scene_ends = {len(sentence_ends(text))} if index + 1 < len(chapters) else set()
        # The toolbox's three cuts now occur after the corresponding complete sentences.
        if name == "12-toolbox":
            scene_ends.update({2, 3, 4})
        scale = (frames / rate) / original_duration
        paced, adjusted, events = add_pauses(
            pcm, rate, timing, scale, args.sentence_pause, args.scene_pause, scene_ends
        )
        with wave.open(str(output / f"{name}-voice.wav"), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(paced)
        (output / f"{name}-alignment.json").write_text(json.dumps(adjusted), encoding="utf-8")
        duration = len(paced) / (2 * rate)
        record = {
            "chapter": name,
            "source_duration": original_duration,
            "reference_duration": reference_duration,
            "tempo_filter": tempo,
            "tempo_duration": frames / rate,
            "duration_seconds": duration,
            "events": events,
            "source_audio_sha256": hashlib.sha256(audio_path.read_bytes()).hexdigest(),
        }
        if name == "12-toolbox":
            boundaries = [0] + [e["pause_end_seconds"] for e in events if e["sentence"] in {2, 3, 4}]
            boundaries.append(duration)
            record["scene_durations"] = [b - a for a, b in zip(boundaries[:-1], boundaries[1:], strict=True)]
        report["chapters"].append(record)
        print(f"Paced {name}: {duration:.1f}s, {len(events)} sentence pauses", flush=True)
    (output / "pacing-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
