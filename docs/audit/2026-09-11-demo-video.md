# Brian-narrated walkthrough — 2026-09-11

The user authorized ElevenLabs narration with the account's Brian voice and requested
that project code, but not the video, be committed. The original walkthrough is retained
separately. Only synthetic tutorial text was sent to ElevenLabs; source footage and
research databases were not uploaded. Credentials were consumed from the user-designated
key file without printing or committing them.

## Production

- Selected the exact **Brian** cloned voice, distinct from Brian HQ and the premade Brian.
- Local professional-explainer preset: multilingual v2, stability 0.62, similarity 0.80,
  style 0.12, speaker boost on, speed 0.96. Account voice settings were not changed.
- Fourteen completed synthesis requests, 5,748 input characters. The initial sample
  chapter was reused rather than synthesized twice.
- Original source captures reused. Ninety captions use ElevenLabs character timing;
  fourteen embedded chapter markers were rebuilt for the new narration.
- Final MP4: H.264/AAC, 1920×1080, 30 fps, duration **6:14.69**, 20,578,781 bytes.
- SHA-256: `df2dff55c7901091df81e7375d3ef97a20c09a2baa60774894904adee9b2c2f0`.
- MP4, audio, screenshots, timing data, receipts, and voice identity metadata remain
  outside Git. Reusable production source is in `scripts/demo_video`.

## Verification

- Final MP4 passed a complete audio/video decode with FFmpeg (exit 0).
- Stream metadata confirmed H.264/AAC, 1080p, and all fourteen chapters.
- Narration was non-silent in every chapter. Representative rendered caption frames
  were inspected for legibility. This is not an independent speech-recognition audit.
- Ten offline tests passed for timing preservation, loopback capture restrictions,
  credential-error redaction, interrupted paid-request protection, and explicit screenshot
  fallback when the browser recorder's encoder fails.
- Ruff passed on the production scripts and new tests; `git diff --check` passed.
- A fresh synthetic local preview passed the complete recorder workflow in
  `--screenshots-only` mode. Pending proposals and human revisions preserved the original
  prose; approval applied the exact reviewed text; undo awaited approval and restored the
  original; the saved brief appeared in context; export completed. No browser JavaScript
  errors were reported. This run used fake application providers and no staging resources.

## Recorder limitations and recovery

Fresh Windows browser startup exposed conflicting installed agent-browser runtimes and
daemon configuration timeouts. The documented initialization step and recorder now pin
`AGENT_BROWSER_HOME` to the intended package; separate session names are supported.
Browser-owned FFmpeg encoding also failed intermittently during repeat capture. The
recorder retains the verified screenshot, records an explicit fallback, and continues
with screenshots instead of reusing a partial WebM or a stale active recording. The
renderer honors that record. The delivered Brian video uses the original successful
captures; it was not rebuilt from the screenshot-only verification run.

The application still uses fake providers in the demonstrated workflow. ElevenLabs
narration does not establish live manuscript-writing quality or authorize real research
on staging. This change does not deploy or change application authentication.
