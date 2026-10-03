"""Assemble captured UI footage, local narration, captions, and chapter metadata."""

import argparse
import array
import json
import math
import re
import subprocess
import wave
from pathlib import Path

OUT = None
FFMPEG = None
FONT = "C:/Windows/Fonts/segoeui.ttf"
BOLD = "C:/Windows/Fonts/segoeuib.ttf"
NAVY = "#101f31"
MUTED = "#9aadc2"
GOLD = "#f1bd62"
WHITE = "#f4f7fb"
CHAPTERS = []
VOICE = "Synthetic narration"


def timed_callouts(chapter, alignment, cues, duration):
    """Resolve unique spoken phrases; never guess a highlight time or offscreen target."""
    text = "".join(alignment["characters"])
    result = []
    for cue in cues:
        if cue["chapter"] != chapter:
            continue
        phrase = cue["phrase"]
        if text.count(phrase) != 1:
            raise ValueError(f"{chapter}: callout phrase must occur exactly once: {phrase}")
        x, y, width, height = cue["box"]
        if cue["viewport"] != [1600, 760] or not (0 <= x < x + width <= 1600 and 48 <= y < y + height <= 760):
            raise ValueError(f"{chapter}: callout is outside the captured viewport")
        start = alignment["character_start_times_seconds"][text.index(phrase)]
        result.append({**cue, "start": start})
    result.sort(key=lambda c: c["start"])
    for i, cue in enumerate(result):
        next_start = result[i + 1]["start"] if i + 1 < len(result) else duration
        cue["end"] = min(next_start, cue["start"] + 6, duration)
        if cue["end"] <= cue["start"]:
            raise ValueError("Callout has no visible duration")
    return result


def callout_scenes(name, cues, duration):
    starts = [0] + [c["start"] for c in cues[1:]]
    ends = starts[1:] + [duration]
    lines = []
    for cue, start, end in zip(cues, starts, ends, strict=True):
        image = cue["image"]
        if not re.fullmatch(r"cue-\d+\.png", image) or not (OUT / image).is_file():
            raise ValueError("Missing or invalid callout screenshot")
        lines.append(f"file '{image}'\nduration {end - start:.6f}\n")
    lines.append(f"file '{cues[-1]['image']}'\n")
    (OUT / f"{name}-scenes.txt").write_text("".join(lines), encoding="utf-8")
    ass = OUT / f"{name}.ass"
    with ass.open("a", encoding="utf-8") as stream:
        for cue in cues:
            x, y, width, height = cue["box"]
            x, y = round(40 + x * 1.15 - 5), round(84 + y * 1.15 - 5)
            right, bottom = round(x + width * 1.15 + 10), round(y + height * 1.15 + 10)
            rectangles = [
                (x, y, right, y + 4),
                (x, bottom - 4, right, bottom),
                (x, y, x + 4, bottom),
                (right - 4, y, right, bottom),
            ]
            path = " ".join(f"m {a} {b} l {c} {b} {c} {d} {a} {d}" for a, b, c, d in rectangles)
            prefix = f"Dialogue: 2,{stamp(cue['start'], True)},{stamp(cue['end'], True)},Default,,0,0,0,,"
            stream.write(prefix + r"{\an7\pos(0,0)\p1\bord0\shad0\1c&H62BDF1&\fad(100,100)}" + path + "\n")
            label = cue["label"]
            if any(c in label for c in "{}\\\n\r"):
                raise ValueError("Invalid callout label")
            label_x = max(48, min(x, 1870 - len(label) * 14))
            label_y = y - 38 if y >= 130 else bottom + 8
            stream.write(
                prefix
                + f"{{\\an7\\pos({label_x},{label_y})\\fs24\\b1\\bord5\\shad0"
                + r"\1c&H62BDF1&\3c&H311F10&\fad(100,100)}"
                + label
                + "\n"
            )


def run(args):
    p = subprocess.run(
        [FFMPEG, "-hide_banner", "-loglevel", "error", "-nostdin", "-y", *args],
        cwd=OUT,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    if p.returncode:
        raise RuntimeError(p.stderr[-4000:])


def seconds(path):
    p = subprocess.run(
        [FFMPEG, "-hide_banner", "-i", str(path)], capture_output=True, encoding="utf-8", errors="replace"
    )
    m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", p.stderr)
    if not m:
        raise ValueError(f"Cannot read video duration: {path.name}")
    return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])


def font(size, bold=False):
    from PIL import ImageFont

    return ImageFont.truetype(BOLD if bold else FONT, size)


def overlay(ch, index):
    from PIL import Image, ImageDraw

    canvas = Image.new("RGBA", (1920, 1080), NAVY)
    draw = ImageDraw.Draw(canvas)
    draw.text((40, 19), ch["title"], font=font(34, True), fill=WHITE)
    draw.rounded_rectangle((1532, 18, 1880, 63), 10, fill="#3b3021", outline=GOLD, width=1)
    draw.text((1706, 40), "SYNTHETIC DATA  /  SIMULATED AI", anchor="mm", font=font(18, True), fill=GOLD)
    draw.rectangle((40, 84, 1880, 958), fill=(0, 0, 0, 0))
    draw.rectangle((0, 1074, int(1920 * (index + 1) / len(CHAPTERS)), 1080), fill=GOLD)
    canvas.save(OUT / f"{ch['id']}-overlay.png")


def card(ch):
    from PIL import Image, ImageDraw

    canvas = Image.new("RGB", (1840, 874), NAVY)
    draw = ImageDraw.Draw(canvas)
    draw.text((95, 105), "PAPER / WORKBENCH", font=font(30, True), fill=GOLD)
    title = (
        "Write with evidence.\nKeep control of every edit."
        if ch["id"] == "00-intro"
        else "Start small.\nBuild a defensible paper."
    )
    draw.multiline_text((95, 182), title, font=font(70, True), fill=WHITE, spacing=12)
    for i, line in enumerate(ch["lines"]):
        y = 455 + 84 * i
        draw.ellipse((98, y + 9, 131, y + 42), fill=GOLD)
        draw.text((156, y), line, font=font(30, True), fill=WHITE)
    draw.text(
        (95, 792), "Recorded from the working application  •  September 2026", font=font(24), fill=MUTED
    )
    canvas.save(OUT / f"{ch['id']}.png")


def stamp(t, ass=False):
    if ass:
        return f"{int(t) // 3600}:{int(t) // 60 % 60:02}:{t % 60:05.2f}"
    ms = round(t * 1000)
    return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"


def aligned_captions(text, alignment):
    """Use provider timings, splitting readable captions without approximating speech speed."""
    if "".join(alignment["characters"]) != text:
        raise ValueError("Narration and alignment text differ")
    starts = alignment["character_start_times_seconds"]
    ends = alignment["character_end_times_seconds"]
    if len(starts) != len(text) or len(ends) != len(text):
        raise ValueError("Incomplete character timing")
    captions = []
    words = list(re.finditer(r"\S+", text))
    begin = 0
    for index, word in enumerate(words):
        next_word = words[index + 1] if index + 1 < len(words) else None
        if (
            word.group().endswith((".", "?", "!"))
            or next_word is None
            or next_word.end() - words[begin].start() > 108
        ):
            lo, hi = words[begin].start(), word.end()
            start, end = starts[lo], ends[hi - 1]
            if end < start or (captions and start < captions[-1][0]):
                raise ValueError("Invalid timing order")
            captions.append((start, end, text[lo:hi]))
            begin = index + 1
    return captions


def narration(ch):
    timing = OUT / f"{ch['id']}-alignment.json"
    if timing.exists():
        with wave.open(str(OUT / f"{ch['id']}-voice.wav"), "rb") as w:
            if w.getsampwidth() != 2 or w.getnchannels() != 1:
                raise ValueError("Expected mono 16-bit narration")
            duration = w.getnframes() / w.getframerate()
            samples = array.array("h", w.readframes(w.getnframes()))
        rms = math.sqrt(sum(s * s for s in samples) / len(samples))
        if rms <= 100:
            raise ValueError("Narration is silent")
        captions = aligned_captions(" ".join(ch["speech"]), json.loads(timing.read_text(encoding="utf-8")))
        if captions[-1][1] > duration + 0.1:
            raise ValueError("Captions extend past audio")
        write_ass(ch, captions)
        return duration, captions, round(rms, 2)
    return legacy_narration(ch)


def legacy_narration(ch):
    waves = []
    for i in range(len(ch["speech"])):
        with wave.open(str(OUT / f"{ch['id']}-{i}.wav"), "rb") as w:
            waves.append((w.getparams(), w.readframes(w.getnframes())))
    p = waves[0][0]
    assert p.sampwidth == 2 and p.nchannels == 1
    rate = p.framerate
    audio = bytearray(b"\0" * (int(rate * 0.45) * 2))
    events = []
    for line, (params, data) in zip(ch["speech"], waves, strict=True):
        assert params[:3] == p[:3]
        start = len(audio) / (rate * 2)
        audio.extend(data)
        end = len(audio) / (rate * 2)
        events.append((start, end, line))
        audio.extend(b"\0" * (int(rate * 0.22) * 2))
    audio.extend(b"\0" * (int(rate * 0.5) * 2))
    duration = len(audio) / (rate * 2)
    samples = array.array("h", audio)
    rms = math.sqrt(sum(s * s for s in samples) / len(samples))
    assert rms > 100, "Narration is silent"
    with wave.open(str(OUT / f"{ch['id']}-voice.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(audio)
    # Split long lines at natural sentence boundaries for readable two-line captions.
    captions = []
    for start, end, line in events:
        pieces = re.split(r"(?<=[.!?])\s+", line)
        weights = [len(piece) for piece in pieces]
        cursor = start
        for piece, weight in zip(pieces, weights, strict=True):
            finish = cursor + (end - start) * weight / sum(weights)
            captions.append((cursor, finish, piece))
            cursor = finish
    write_ass(ch, captions)
    return duration, captions, round(rms, 2)


def write_ass(ch, captions):
    ass = "[Script Info]\nPlayResX: 1920\nPlayResY: 1080\nWrapStyle: 0\n\n[V4+ Styles]\n"
    ass += (
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
    )
    ass += (
        "Style: Default,Segoe UI,29,&H00FFFFFF,&H00FFFFFF,&H00101F31,&H00101F31,"
        "0,0,0,0,100,100,0,0,1,0,0,2,80,80,34,1\n\n[Events]\n"
    )
    ass += "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    for start, end, line in captions:
        ass += f"Dialogue: 0,{stamp(start, True)},{stamp(end, True)},Default,,0,0,0,,{line}\n"
    (OUT / f"{ch['id']}.ass").write_text(ass, encoding="utf-8-sig")


def main():
    global OUT, FFMPEG, CHAPTERS, VOICE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--ffmpeg", required=True, help="Path to an FFmpeg executable with libass.")
    args = parser.parse_args()
    OUT = args.input_dir.resolve()
    FFMPEG = args.ffmpeg
    CHAPTERS = json.loads((OUT / "narration.json").read_text(encoding="utf-8"))
    if (OUT / "voice-profile.json").exists():
        profile = json.loads((OUT / "voice-profile.json").read_text(encoding="utf-8"))
        VOICE = profile["provider"] + " / " + profile["voice_name"]
    capture_report = OUT / "capture-verification.json"
    fallbacks = (
        json.loads(capture_report.read_text(encoding="utf-8")).get("recording_fallbacks", [])
        if capture_report.exists()
        else []
    )
    timeline, subtitles, report = [], [], []
    pacing_file = OUT / "pacing-report.json"
    pacing = json.loads(pacing_file.read_text(encoding="utf-8")) if pacing_file.exists() else {}
    scene_durations = {
        c["chapter"]: c["scene_durations"] for c in pacing.get("chapters", []) if "scene_durations" in c
    }
    cues_file = OUT / "callouts.json"
    cues = json.loads(cues_file.read_text(encoding="utf-8")) if cues_file.exists() else []
    all_callouts = []
    offset = 0
    for index, ch in enumerate(CHAPTERS):
        name = ch["id"]
        overlay(ch, index)
        duration, captions, rms = narration(ch)
        chapter_cues = []
        if cues and not ch.get("card"):
            alignment = json.loads((OUT / f"{name}-alignment.json").read_text(encoding="utf-8"))
            chapter_cues = timed_callouts(name, alignment, cues, duration)
            if not chapter_cues:
                raise ValueError(f"{name}: missing callouts")
            all_callouts.extend({**c, "global_start": offset + c["start"]} for c in chapter_cues)
        timeline.append((offset, ch["title"]))
        subtitles.extend((offset + s, offset + e, text) for s, e, text in captions)
        if ch.get("card"):
            card(ch)
            source = ["-loop", "1", "-i", f"{name}.png"]
            speed = "setpts=PTS-STARTPTS"
        elif chapter_cues:
            callout_scenes(name, chapter_cues, duration)
            source = ["-f", "concat", "-safe", "0", "-i", f"{name}-scenes.txt"]
            speed = "setpts=PTS-STARTPTS"
        elif name in fallbacks:
            source = ["-loop", "1", "-i", f"{name}.png"]
            speed = "setpts=PTS-STARTPTS"
        elif name == "12-toolbox":
            # The recorder could not finalize the multi-navigation clip; show its verified frames.
            frames = ["12-literature.png", "12-compute.png", "12-figures.png", "12-toolbox.png"]
            holds = scene_durations.get(name, [duration / 4] * 4)
            (OUT / "toolbox-images.txt").write_text(
                "".join(f"file '{f}'\nduration {hold:.4f}\n" for f, hold in zip(frames, holds, strict=True))
                + f"file '{frames[-1]}'\n",
                encoding="utf-8",
            )
            source = ["-f", "concat", "-safe", "0", "-i", "toolbox-images.txt"]
            speed = "setpts=PTS-STARTPTS"
        else:
            raw = seconds(OUT / f"{name}.webm")
            source = ["-i", f"{name}.webm"]
            # Slow quick automated actions modestly, then hold the verified final state.
            multiplier = min(1.7, (duration - 1) / raw)
            speed = (
                f"setpts={multiplier:.6f}*(PTS-STARTPTS),tpad=stop_mode=clone:stop_duration={duration:.3f}"
            )
        filters = (
            f"[0:v]{speed},fps=30,scale=1840:874:force_original_aspect_ratio=decrease,"
            "pad=1840:874:(ow-iw)/2:(oh-ih)/2:color=0x101f31,setsar=1[v];"
            f"[1:v][v]overlay=40:84,subtitles={name}.ass,format=yuv420p[out]"
        )
        run(
            [
                *source,
                "-loop",
                "1",
                "-i",
                f"{name}-overlay.png",
                "-i",
                f"{name}-voice.wav",
                "-filter_complex",
                filters,
                "-map",
                "[out]",
                "-map",
                "2:a",
                "-t",
                f"{duration:.4f}",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "20",
                "-r",
                "30",
                "-c:a",
                "aac",
                "-b:a",
                "160k",
                "-ar",
                "48000",
                "-af",
                "anull" if (OUT / "audio-cleanup.json").exists() else "loudnorm=I=-16:TP=-1.5:LRA=11",
                "-movflags",
                "+faststart",
                f"{name}-final.mp4",
            ]
        )
        report.append({"chapter": name, "duration_seconds": round(duration, 3), "narration_rms": rms})
        offset += duration
        print(f"Encoded {name}: {duration:.1f}s", flush=True)
    (OUT / "concat.txt").write_text(
        "".join(f"file '{c['id']}-final.mp4'\n" for c in CHAPTERS), encoding="utf-8"
    )
    meta = (
        ";FFMETADATA1\ntitle=Paper-Workbench: Evidence to Reviewed Manuscript\n"
        "artist=Paper-Workbench walkthrough\ncomment=Actual local UI; synthetic research; "
        f"simulated AI; narration by {VOICE}.\n"
    )
    for i, (start, title) in enumerate(timeline):
        end = timeline[i + 1][0] if i + 1 < len(timeline) else offset
        meta += (
            f"[CHAPTER]\nTIMEBASE=1/1000\nSTART={round(start * 1000)}\n"
            f"END={round(end * 1000)}\ntitle={title}\n"
        )
    (OUT / "chapters.ffmeta").write_text(meta, encoding="utf-8")
    master = (OUT / "master-voice.wav").exists()
    run(
        [
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            "concat.txt",
            "-i",
            "chapters.ffmeta",
            *(["-i", "master-voice.wav", "-map", "0:v:0", "-map", "2:a:0"] if master else []),
            "-map_metadata",
            "1",
            "-map_chapters",
            "1",
            *(["-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-ar", "48000"] if master else ["-c", "copy"]),
            "-movflags",
            "+faststart",
            "Paper-Workbench-Walkthrough.mp4",
        ]
    )
    srt = (
        "\n\n".join(f"{i + 1}\n{stamp(s)} --> {stamp(e)}\n{t}" for i, (s, e, t) in enumerate(subtitles))
        + "\n"
    )
    (OUT / "Paper-Workbench-Walkthrough.srt").write_text(srt, encoding="utf-8")
    transcript = (
        "# Paper-Workbench video walkthrough\n\nActual local interface; synthetic research; "
        f"fake AI provider; narration by {VOICE}.\n\n"
    )
    for (start, title), ch in zip(timeline, CHAPTERS, strict=True):
        transcript += (
            f"## {int(start) // 60:02}:{int(start) % 60:02} — {title}\n\n"
            + "\n\n".join(ch["speech"])
            + "\n\n"
        )
    (OUT / "Walkthrough-transcript.md").write_text(transcript, encoding="utf-8")
    (OUT / "render-verification.json").write_text(
        json.dumps(
            {
                "duration_seconds": offset,
                "resolution": "1920x1080",
                "fps": 30,
                "chapters": report,
                "caption_count": len(subtitles),
                "data": "synthetic",
                "voice": VOICE,
                "callouts": all_callouts,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"FINAL: {offset:.1f}s", flush=True)


if __name__ == "__main__":
    main()
