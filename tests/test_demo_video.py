"""Offline checks for narration timing, credential handling, and capture boundaries."""

import importlib.util
import io
import json
import sys
import urllib.error
from pathlib import Path

import pytest


def load_script(name):
    path = Path(__file__).resolve().parents[1] / "scripts" / "demo_video" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_caption_chunks_preserve_text_and_provider_timing():
    render = load_script("render_demo")
    text = "Evidence first. " + "A carefully bounded observation needs supporting evidence. " * 4
    text = text.strip()
    alignment = {
        "characters": list(text),
        "character_start_times_seconds": [i / 10 for i in range(len(text))],
        "character_end_times_seconds": [(i + 1) / 10 for i in range(len(text))],
    }
    captions = render.aligned_captions(text, alignment)
    assert " ".join(item[2] for item in captions) == text
    assert all(len(item[2]) <= 108 for item in captions)
    for start, end, line in captions:
        assert text[round(start * 10) : round(end * 10)] == line
    alignment["characters"][0] = "X"
    with pytest.raises(ValueError, match="differ"):
        render.aligned_captions(text, alignment)


@pytest.mark.parametrize(
    "prefix",
    [
        "https://example.com",
        "http://localhost",
        "http://127.0.0.1.evil.test",
        "http://user@127.0.0.1",
        "https://127.0.0.1",
    ],
)
def test_capture_refuses_non_demo_origins(prefix):
    record = load_script("record_demo")
    fragment = "/project/" + "a" * 32 + "/manuscripts/" + "b" * 32 + "/" + "c" * 32
    with pytest.raises(ValueError):
        record.parse_demo_url(prefix + "/ui/#" + fragment)
    base, *_ = record.parse_demo_url("http://127.0.0.1:8879/ui/#" + fragment)
    assert base == "http://127.0.0.1:8879"


def test_api_key_loader_only_uses_named_entry(tmp_path, monkeypatch):
    module = load_script("elevenlabs_narrate")
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    path = tmp_path / "synthetic-config.txt"
    path.write_text('UNRELATED=ignore-me\nELEVENLABS_API_KEY="synthetic-test-value"\n')
    assert module.load_key(path) == "synthetic-test-value"


def test_service_error_does_not_expose_body(monkeypatch):
    module = load_script("elevenlabs_narrate")

    def fail(*args, **kwargs):
        raise urllib.error.HTTPError(
            "https://api.elevenlabs.io", 403, "blocked", {}, io.BytesIO(b"synthetic sensitive response")
        )

    monkeypatch.setattr(module.urllib.request, "urlopen", fail)
    with pytest.raises(SystemExit) as error:
        module.request("synthetic-test-key", "/v2/voices")
    assert str(error.value) == "ElevenLabs returned HTTP 403; response body withheld."


def test_incomplete_receipt_blocks_duplicate_paid_request(tmp_path, monkeypatch):
    module = load_script("elevenlabs_narrate")
    narration = tmp_path / "narration.json"
    narration.write_text(json.dumps([{"id": "intro", "speech": ["Synthetic tutorial."]}]))
    monkeypatch.setattr(
        sys,
        "argv",
        ["narrate", "--voice-id", "test-voice", "--narration", str(narration), "--output-dir", str(tmp_path)],
    )
    monkeypatch.setattr(module, "load_key", lambda _: "synthetic-test-key")
    paid_calls = []

    def request(key, path, payload=None):
        if payload is None:
            return {"name": "Synthetic test voice"}
        paid_calls.append(path)
        raise SystemExit("Simulated interrupted response")

    monkeypatch.setattr(module, "request", request)
    with pytest.raises(SystemExit, match="interrupted"):
        module.main()
    with pytest.raises(SystemExit, match="incomplete"):
        module.main()
    assert len(paid_calls) == 1


def test_encoder_failure_is_an_explicit_screenshot_fallback(monkeypatch):
    module = load_script("record_demo")
    screenshots = []
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    monkeypatch.setattr(module, "shot", screenshots.append)

    def failed_encoder(*args):
        raise RuntimeError("ffmpeg failed: synthetic encoder failure")

    monkeypatch.setattr(module, "browser", failed_encoder)
    module.stop("05-dialogue")
    assert screenshots == ["05-dialogue"]
    assert module.RECORDING_FALLBACKS == ["05-dialogue"]


def test_sentence_pauses_preserve_audio_and_shift_captions():
    pace = load_script("pace_demo")
    text = "One. Two!"
    timing = {
        "characters": list(text),
        "character_start_times_seconds": [i / 10 for i in range(len(text))],
        "character_end_times_seconds": [(i + 1) / 10 for i in range(len(text))],
    }
    pcm = b"\1\0" * 1000
    audio, shifted, events = pace.add_pauses(pcm, 1000, timing, 1, 0.25, 0.1, {1})
    assert len(audio) == 3200  # One second + .35s scene pause + .25s final sentence pause.
    assert audio[:890] == pcm[:890]
    assert audio[898:900] == b"\0\0"
    assert audio[900:1600] == b"\0" * 700
    assert audio[1600:1602] == b"\0\0"
    assert audio[1610:2690] == pcm[910:1990]
    assert audio[2700:] == b"\0" * 500
    assert shifted["character_start_times_seconds"][5] == pytest.approx(0.85)
    assert shifted["character_end_times_seconds"][-1] == pytest.approx(1.25)
    assert [event["scene_change"] for event in events] == [True, False]


def test_sentence_boundaries_skip_decimal_points_and_keep_closing_quotes():
    pace = load_script("pace_demo")
    text = 'The result is 3.5 percent. He said "Check it!" Next?'
    ends = pace.sentence_ends(text)
    assert len(ends) == 3
    assert text[: ends[0]] == "The result is 3.5 percent."
    assert text[ends[0] : ends[1]].strip() == 'He said "Check it!"'


def test_continuous_take_split_preserves_samples_and_aligned_words(tmp_path):
    import wave

    module = load_script("elevenlabs_narrate")
    chapters = [{"id": "one", "speech": ["First."]}, {"id": "two", "speech": ["Next."]}]
    text = "First. Next."
    alignment = {
        "characters": list(text),
        "character_start_times_seconds": [i / 10 for i in range(len(text))],
        "character_end_times_seconds": [(i + 1) / 10 for i in range(len(text))],
    }
    (tmp_path / "continuous-alignment.json").write_text(json.dumps(alignment))
    original = b"\x10\x01" * 1300
    with wave.open(str(tmp_path / "continuous-voice.wav"), "wb") as audio:
        audio.setparams((1, 2, 1000, 0, "NONE", "not compressed"))
        audio.writeframes(original)
    module.split_take(tmp_path, chapters)
    samples = b""
    for ch in chapters:
        with wave.open(str(tmp_path / f"{ch['id']}-voice.wav"), "rb") as audio:
            samples += audio.readframes(audio.getnframes())
    assert samples == original
    second = json.loads((tmp_path / "two-alignment.json").read_text())
    assert "".join(second["characters"]) == "Next."
    assert second["character_start_times_seconds"][0] == pytest.approx(0.05)


def test_callouts_follow_spoken_phrases_and_reject_ambiguous_or_offscreen_targets():
    render = load_script("render_demo")
    text = "Inspect it. Apply shown edit."
    alignment = {
        "characters": list(text),
        "character_start_times_seconds": [i / 10 for i in range(len(text))],
    }
    cue = {
        "chapter": "apply",
        "phrase": "Apply shown edit",
        "box": [100, 200, 120, 30],
        "viewport": [1600, 760],
    }
    result = render.timed_callouts("apply", alignment, [cue], 4)
    assert result[0]["start"] == pytest.approx(1.2)
    assert result[0]["end"] == 4
    with pytest.raises(ValueError, match="exactly once"):
        render.timed_callouts("apply", alignment, [{**cue, "phrase": "missing"}], 4)
    with pytest.raises(ValueError, match="outside"):
        render.timed_callouts("apply", alignment, [{**cue, "box": [100, 740, 120, 30]}], 4)
