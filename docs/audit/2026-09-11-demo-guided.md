# Guided Brian walkthrough revision — 2026-09-11

Requested: 92% of the original Brian recording's speed, more enthusiastic explanatory
delivery, reduced background acoustics at scene changes, and highlights on referenced UI.

The same selected Brian clone was synthesized in one continuous multilingual-v2 take.
The engaged preset uses stability 0.45, similarity 0.65, style 0.30, speaker boost off,
and API speed 0.96. This requests more expression without inserting spoken direction
text or changing the account's saved voice settings. Only the synthetic tutorial text
was sent to ElevenLabs. A paid-request receipt prevents silent duplicate synthesis.

The continuous take received a 70 Hz high-pass, 12 dB FFT noise reduction, soft downward
expansion in quiet passages, and a measured whole-take loudness pass. Previous versions
normalized each chapter independently; this edition avoids that source of changing
background gain. No music or room tone was added. These signal-processing checks do
not certify perceived enthusiasm or the absence of all voice-clone artifacts.

Each chapter was retimed to the original Brian chapter duration divided by 0.92,
preserving pitch. Maximum measured endpoint error was 0.019 seconds. The existing
80 additional quarter-second sentence pauses and sixteen 0.1-second transition increments
were retained, including five-millisecond fades at inserted silence edges.

Fresh synthetic UI captures include **55** phrase-linked targets across all twelve
application chapters. Gold outlines and labels use actual DOM bounds and retimed
character alignment. Intermediate states include an unsaved revision with disabled
approval, the reviewed replacement, pending undo, restored text, and exported files.
Abstract methodological cautions remain subtitles rather than receiving arbitrary boxes.
The guided edition switches between captured states as the narration reaches them.

Verification:

- All seven synthetic UI/API checks passed; browser error output was empty.
- All 55 phrases resolved uniquely and every target was inside the captured viewport.
- All 55 rendered midpoint frames contained their expected outlines; the contact sheet
  was visually inspected, with a full-size inspection of disabled approval and its caption.
- All 80 inserted PCM pauses contained zero samples; reference pacing checks passed.
- Fourteen offline production-tool tests passed. Ruff and `git diff --check` passed.
- The final MP4 passed a complete audio/video decode: H.264/AAC, 1920×1080, 30 fps,
  fourteen embedded chapters, ninety caption cues, duration **7:08.70**.
- Final encoded audio measured **-16.21 LUFS**, **-1.34 dBTP**, loudness range **3.70 LU**.
- File size: **17,099,772 bytes**.
- SHA-256: `1ebd118d3f45e2e2952c018e6462705267e683362381947d5bb59f51f1063fe1`.

Local artifact folder: `output/paper-workbench-demo-brian-guided-20260911` under the
parent workspace. Earlier versions are preserved. Generated video, audio, screenshots,
voice identifiers, and credentials remain outside Git; production code, tests, and
instructions are versioned. No application deployment was changed.
