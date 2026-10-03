"""Generate tutorial narration using an explicitly selected ElevenLabs voice.

Only the named API-key entry is consumed from an explicitly supplied dotenv file.
Credentials and raw service error bodies are never logged or saved.
"""

import argparse
import base64
import hashlib
import json
import os
import urllib.error
import urllib.request
import wave
from pathlib import Path

PROFESSIONAL_EXPLAINER = {
    "stability": 0.62,
    "similarity_boost": 0.8,
    "style": 0.12,
    "use_speaker_boost": True,
    "speed": 0.96,
}
ENGAGED_EXPLAINER = {
    "stability": 0.45,
    "similarity_boost": 0.65,
    "style": 0.3,
    "use_speaker_boost": False,
    "speed": 0.96,
}
WARM_EXPLAINER = {
    "stability": 0.5,
    "similarity_boost": 0.55,
    "style": 0.45,
    "use_speaker_boost": False,
    "speed": 0.88,
}


def split_take(output, chapters):
    """Split a continuous take between chapters without cutting aligned speech."""
    alignment = json.loads((output / "continuous-alignment.json").read_text(encoding="utf-8"))
    texts = [" ".join(ch["speech"]) for ch in chapters]
    if "".join(alignment["characters"]) != " ".join(texts):
        raise ValueError("Continuous take text differs")
    with wave.open(str(output / "continuous-voice.wav"), "rb") as audio:
        rate = audio.getframerate()
        pcm = audio.readframes(audio.getnframes())
    offsets, cursor = [], 0
    for text in texts:
        offsets.append(cursor)
        cursor += len(text) + 1
    starts = alignment["character_start_times_seconds"]
    ends = alignment["character_end_times_seconds"]
    cuts = [0]
    for i in range(1, len(texts)):
        left = ends[offsets[i - 1] + len(texts[i - 1]) - 1]
        right = starts[offsets[i]]
        if right < left:
            raise ValueError("Overlapping chapter speech requires inspection")
        cuts.append(round((left + right) / 2 * rate))
    cuts.append(len(pcm) // 2)
    for i, (chapter, text) in enumerate(zip(chapters, texts, strict=True)):
        lo, hi = cuts[i], cuts[i + 1]
        with wave.open(str(output / f"{chapter['id']}-voice.wav"), "wb") as audio:
            audio.setparams((1, 2, rate, 0, "NONE", "not compressed"))
            audio.writeframes(pcm[lo * 2 : hi * 2])
        first = offsets[i]
        timing = {"characters": list(text)}
        for field in ("character_start_times_seconds", "character_end_times_seconds"):
            timing[field] = [
                max(0, min((hi - lo) / rate, t - lo / rate))
                for t in alignment[field][first : first + len(text)]
            ]
        (output / f"{chapter['id']}-alignment.json").write_text(json.dumps(timing), encoding="utf-8")


def load_key(env_file=None):
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not key and env_file:
        with Path(env_file).open(encoding="utf-8-sig") as stream:
            for line in stream:
                name, sep, value = line.strip().removeprefix("export ").partition("=")
                if sep and name.strip() == "ELEVENLABS_API_KEY":
                    key = value.strip().strip("\"'")
                    break
    if not key:
        raise SystemExit("ELEVENLABS_API_KEY is missing; no service request was made.")
    return key


def request(key, path, payload=None):
    body = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        "https://api.elevenlabs.io" + path,
        data=body,
        headers={"xi-api-key": key, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"ElevenLabs returned HTTP {exc.code}; response body withheld.") from None
    except urllib.error.URLError:
        raise SystemExit("ElevenLabs connection failed; no credential details logged.") from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--list-brian", action="store_true")
    parser.add_argument("--voice-id")
    parser.add_argument("--narration", type=Path, default=Path(__file__).with_name("narration.json"))
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--only", help="Generate just this chapter; completed chapters are reusable.")
    parser.add_argument(
        "--single-take", action="store_true", help="Generate all chapters together for continuity."
    )
    parser.add_argument("--preset", choices=["professional", "engaged", "warm"], default="professional")
    parser.add_argument("--seed", type=int, default=20260911)
    args = parser.parse_args()
    key = load_key(args.env_file)
    if args.list_brian:
        result = request(key, "/v2/voices?search=Brian&page_size=100")
        print(
            json.dumps(
                [
                    {
                        field: voice.get(field)
                        for field in ("voice_id", "name", "category", "labels", "description")
                    }
                    for voice in result.get("voices", [])
                ],
                indent=2,
            )
        )
        return
    if not args.voice_id or not args.output_dir:
        parser.error("Generation requires --voice-id and --output-dir.")
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    chapters = json.loads(args.narration.read_text(encoding="utf-8"))
    original_chapters = chapters
    if args.single_take:
        if args.only:
            parser.error("--single-take cannot be combined with --only")
        chapters = [{"id": "continuous", "speech": [" ".join(" ".join(ch["speech"]) for ch in chapters)]}]
        if len(chapters[0]["speech"][0]) > 10000:
            parser.error("Continuous multilingual v2 narration must fit 10,000 characters")
    texts = [" ".join(ch["speech"]) for ch in chapters]
    settings = ENGAGED_EXPLAINER if args.preset == "engaged" else PROFESSIONAL_EXPLAINER
    if args.preset == "warm":
        settings = WARM_EXPLAINER
    voice = request(key, "/v1/voices/" + args.voice_id)
    profile = {
        "voice_name": voice["name"],
        "voice_id": args.voice_id,
        "model": "eleven_multilingual_v2",
        "preset": args.preset + "_explainer",
        "direction": "Local preset; voice settings control expressiveness. No direction text is spoken.",
        "voice_settings": settings,
        "single_take": args.single_take,
        "provider": "ElevenLabs",
        "sample_rate": 22050,
    }
    for index, ch in enumerate(chapters):
        name = ch["id"]
        if args.only and args.only != name:
            continue
        payload = {
            "text": texts[index],
            "model_id": profile["model"],
            "voice_settings": settings,
            "seed": args.seed,
        }
        if index:
            payload["previous_text"] = texts[index - 1]
        if index + 1 < len(texts):
            payload["next_text"] = texts[index + 1]
        fingerprint = hashlib.sha256(
            json.dumps({"voice_id": args.voice_id, "payload": payload}, sort_keys=True).encode()
        ).hexdigest()
        receipt_path = output / f"{name}-generation.json"
        audio_path = output / f"{name}-voice.wav"
        timing_path = output / f"{name}-alignment.json"
        if receipt_path.exists():
            saved = json.loads(receipt_path.read_text(encoding="utf-8"))
            if saved.get("fingerprint") != fingerprint:
                raise SystemExit(f"{name}: inputs changed; choose a new output directory.")
            if saved.get("status") == "complete" and audio_path.exists() and timing_path.exists():
                print(f"Reusing {name}", flush=True)
                continue
            raise SystemExit(
                f"{name}: previous generation is incomplete; inspect before retrying a paid request."
            )
        receipt = {"fingerprint": fingerprint, "status": "started", "characters": len(texts[index])}
        receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        result = request(
            key, f"/v1/text-to-speech/{args.voice_id}/with-timestamps?output_format=pcm_22050", payload
        )
        pcm = base64.b64decode(result["audio_base64"], validate=True)
        alignment = result.get("alignment")
        if not alignment or "".join(alignment["characters"]) != texts[index]:
            raise SystemExit(
                f"{name}: original-text alignment is missing or differs; generation requires inspection."
            )
        if len(pcm) < 4400 or len(pcm) % 2:
            raise SystemExit(f"{name}: invalid PCM response.")
        with wave.open(str(audio_path), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(22050)
            audio.writeframes(pcm)
        timing_path.write_text(json.dumps(alignment), encoding="utf-8")
        receipt.update(
            status="complete", duration_seconds=len(pcm) / 44100, audio_sha256=hashlib.sha256(pcm).hexdigest()
        )
        receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        print(f"Generated {name}: {receipt['duration_seconds']:.1f}s", flush=True)
    (output / "voice-profile.json").write_text(json.dumps(profile, indent=2), encoding="utf-8")
    if args.single_take:
        split_take(output, original_chapters)
    (output / "narration.json").write_text(json.dumps(original_chapters, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
