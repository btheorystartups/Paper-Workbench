# Reproduce the narrated software walkthrough

These scripts retain the source for the demonstration without checking video, audio,
screenshots, credentials, or generated account metadata into Git. Use an output directory
outside the checkout. The original Windows-voice video and the ElevenLabs Brian version
are separate local artifacts.

## Requirements

- The project's Python environment, including Pillow for title cards and frame overlays.
- FFmpeg with H.264, AAC, and libass support.
- For fresh capture: agent-browser 0.27.0 and Chrome. Pass the native executable paths.
- For ElevenLabs synthesis: an authorized API key and the exact selected voice ID.

## Capture the synthetic application

Start `scripts/preview_manuscript_chat.py` with `src` on `PYTHONPATH`, as described in
[the demo guide](../../docs/MANUSCRIPT-CHAT.md#offline-demo). Keep that process running.
The generated URL contains fresh fixture IDs. Initialize a fresh browser session from
the shell before running the recorder. This avoids a Windows daemon-configuration timeout
observed when a Python child process both launches and configures a new browser.

```powershell
$env:AGENT_BROWSER_HOME = '<path to the agent-browser 0.27.0 package directory>'
npx --yes agent-browser@0.27.0 --session wb-demo-video `
  --executable-path '<path to chrome.exe>' open '<exact loopback URL printed by the preview>'

python scripts/demo_video/record_demo.py `
  --demo-url '<exact loopback URL printed by the preview>' `
  --agent-browser '<path to agent-browser executable>' `
  --output-dir '<new folder outside the checkout>'
```

The recorder pins `AGENT_BROWSER_HOME` to the package containing the supplied native
executable. Set the same location when initializing the session, especially if multiple
agent-browser versions are installed. `--session` can select a separate session name;
use that same name in both commands.

Capture refuses non-loopback URLs, authenticated or live-provider deployments, and
unexpected seed content. It verifies the review/approval boundaries through the real API
while recording UI actions. Chapters 1–11 use browser recordings; the toolbox overview
uses screenshots. If the browser recorder's encoder fails, the captured real UI screenshot
is retained as an explicit chapter fallback. `capture-verification.json` records checks
and any such fallback, and the renderer avoids the partial WebM. After an encoder failure,
remaining chapters use screenshots to avoid the recorder's stale active-recording state.
Use `--screenshots-only` for a complete UI/API verification run without the browser encoder.

The browser closes when capture ends. Stop the preview process afterward; its temporary
database and exported artifacts are disposable. The captured media remains in your
chosen output folder. To change only the narration, reuse those existing captures.

## Generate the professional-explainer narration

The preset is a local production choice, not a named ElevenLabs API archetype:

| Setting | Value |
| --- | --- |
| Delivery | Professional explainer / informative and educational |
| Direction | Calm, clear, measured, restrained emphasis |
| Model | `eleven_multilingual_v2` |
| Stability | 0.62 |
| Similarity | 0.80 |
| Style | 0.12 |
| Speaker boost | Enabled |
| Speed | 0.96 |

Voice identity and prose also influence delivery. These settings apply to each synthesis
request; the scripts do not change the account's stored voice settings. The production
run used the account's exact **Brian** cloned voice, not the premade Brian voice or Brian HQ.
The voice ID is supplied at runtime and recorded only with the generated media.

```powershell
python scripts/demo_video/elevenlabs_narrate.py --env-file '<key file>' --list-brian

python scripts/demo_video/elevenlabs_narrate.py `
  --env-file '<key file>' `
  --voice-id '<selected voice ID>' `
  --output-dir '<folder containing the captures>'
```

An existing process environment variable takes precedence. Otherwise only the
`ELEVENLABS_API_KEY` entry is consumed from the explicitly named file; `.env.txt` works
too. The key is never printed, saved with artifacts, or added to Git. Only the tutorial
text is sent to ElevenLabs; source footage and research databases are not uploaded.

Each chapter receives one synthesis request with character timing. Completed chapters
are reused when the inputs match. A changed request or an incomplete receipt stops the
run rather than silently issuing another paid request. Inspect an interrupted generation
before choosing whether to retry in a fresh output directory. `--only 00-intro` generates
a single sample chapter. `narration.json` is the editable source script.

See ElevenLabs' [speech timing API](https://elevenlabs.io/docs/api-reference/text-to-speech/convert-with-timestamps)
and [voice settings guide](https://elevenlabs.io/docs/eleven-creative/playground/text-to-speech).

## Render and verify

### Natural sentence joins (current edition)

The September 12 edition uses another fresh `--single-take --preset warm --seed 20260912`
generation. The warm preset uses stability 0.50, similarity 0.55, style 0.45,
speaker boost off, and native speed 0.88. This requests stronger expression from Brian.
Its natural duration was already about 7:09.

```powershell
python scripts/demo_video/continuous_narration.py `
  --input-dir '<fresh continuous take>' --output-dir '<new natural edition folder>' `
  --assets-dir '<previous guided edition folder>' --duration 428.587 `
  --ffmpeg '<path to ffmpeg.exe>'
```

This preserves natural sentence pauses and uses one fixed gain, with peak headroom.
It does not insert digital silence, gate quiet material, or apply adaptive denoising.
Native speed is retained when the take is within 2% of the requested duration;
otherwise one global tempo adjustment is used. Section audio is split only to time
the visuals. When `master-voice.wav` exists, the renderer encodes that uninterrupted
master once as the final soundtrack, avoiding AAC joins between chapter clips.
Run the renderer and `verify_guided.py` against the new folder. Verification also
requires the chapter PCM to reconstruct the master exactly.

This addresses possible processing-induced changes at sentence boundaries. It does
not prove that the synthesized voice contains no acoustic artifacts; perceived
enthusiasm and residual background changes still require listening.

### Continuous, engaged narration with guided highlights

For the guided edition, capture with `--screenshots-only --callouts`. This records
55 phrase-linked screenshots and the real DOM bounds of each highlighted element,
including controls before their state changes. Targets must be fully visible. The
generated `callouts.json` contains only synthetic interface metadata.

Generate a separate continuous take with `elevenlabs_narrate.py --single-take --preset engaged`.
This preset uses stability 0.45, similarity 0.65, style 0.30, speaker boost off, and
speed 0.96. It requests more expression while retaining the selected voice. These are
settings, not a guarantee of a particular emotional performance. One take avoids
independent chapter performances. Original character timings determine safe chapter cuts;
the original complete take and paid-request receipt remain available for inspection.

```powershell
python scripts/demo_video/clean_take.py `
  --input-dir '<continuous take folder>' --output-dir '<new cleaned folder>' `
  --assets-dir '<existing capture folder>' --ffmpeg '<path to ffmpeg.exe>'

python scripts/demo_video/pace_demo.py `
  --input-dir '<cleaned folder>' --output-dir '<new guided folder>' `
  --reference-dir '<original Brian narration folder>' --speed 0.92 `
  --sentence-pause 0.25 --scene-pause 0.1 --ffmpeg '<path to ffmpeg.exe>'

Copy-Item -LiteralPath '<callout capture folder>/callouts.json' -Destination '<guided folder>'
Get-ChildItem -LiteralPath '<callout capture folder>' -Filter 'cue-*.png' |
  Copy-Item -Destination '<guided folder>'
```

`clean_take.py` applies a 70 Hz high-pass filter, gentle FFT noise reduction, a soft
downward expander for quiet material, and one measured loudness pass across the whole
take. The renderer detects `audio-cleanup.json` and avoids normalizing chapters again.
This reduces background sound and chapter gain changes without adding music or room tone.
Listen to the output when judging residual voice-clone artifacts; signal checks cannot
establish subjective audio quality.

With `--reference-dir`, each new chapter's pre-pause duration matches the reference
chapter divided by 0.92, within FFmpeg endpoint rounding. Pitch is preserved. This
prevents a differently paced synthesis from changing the meaning of “92% of the original.”

Render the guided folder using the command below. The renderer resolves every callout
phrase against the retimed character alignment, rejects missing or ambiguous phrases,
switches to the matching captured state, and draws a gold outline and label for up to
six seconds. Highlights are timed annotations; small viewport changes between highlighted
controls do not insert additional narration pauses. Abstract cautions without an interface
target receive subtitles rather than a misleading box. The render report includes all
callout times, labels, source screenshots, and captured bounds.

Run `verify_guided.py --input-dir '<guided folder>' --ffmpeg '<path to ffmpeg.exe>'`
to extract a midpoint frame for every highlight, check its rendered outline, verify
inserted PCM silence and the reference pacing, and generate a contact sheet and checksum.
Inspect that contact sheet and decode the final MP4 as well; outline detection does not
prove that an editorially chosen target is appropriate.

### Slow an existing narration and add pauses

Use a separate output folder to preserve the previous version. This step uses local
FFmpeg `atempo` processing to preserve pitch and does not call ElevenLabs:

```powershell
python scripts/demo_video/pace_demo.py `
  --input-dir '<existing narrated capture folder>' `
  --output-dir '<new empty paced-version folder>' `
  --ffmpeg '<path to ffmpeg.exe>' `
  --speed 0.9 --sentence-pause 0.25 --scene-pause 0.1
```

Speed is relative to the input recording. Sentence pauses are **additional** to existing
pauses. The extra scene pause is added at each chapter transition and at the three toolbox
cuts; there is no transition addition after the final chapter. Toolbox cuts are moved to
complete sentence boundaries. Five-millisecond fades at inserted silence edges avoid
clicks without removing samples or changing timing. `pacing-report.json` records every inserted silence span,
the source audio hashes, and updated scene durations. Character timings are retimed for
the slowed audio and inserted pauses, so captions remain synchronized. Narration input
is the checked-in script's sentence structure; decimal points and filenames do not count
as sentence ends.

Run the renderer below against the new paced folder. It honors those updated scene holds.

### Render the selected version

```powershell
python scripts/demo_video/render_demo.py `
  --input-dir '<folder containing captures and narration>' `
  --ffmpeg '<path to ffmpeg.exe>'
```

The renderer uses the new audio durations and character timings to rebuild captions and
chapter markers. It produces a 1080p H.264/AAC MP4, SRT captions, a timed transcript, and
a render report. It normalizes narration loudness and holds the verified final UI state
after each short recorded interaction. Rerendering replaces generated files in that
output folder; keep distinct folders for alternate versions.

Decode the final file with FFmpeg before delivery, and inspect representative frames for
legibility. The offline tests in `tests/test_demo_video.py` exercise credential handling,
capture origin restrictions, timing integrity, and interrupted-generation behavior.
