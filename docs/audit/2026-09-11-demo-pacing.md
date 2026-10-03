# Brian walkthrough pacing revision — 2026-09-11

Requested: slower narration, approximately 90% speed, plus 0.25 seconds after sentence
ends and another 0.1 seconds at scene changes.

The revision reuses the existing Brian audio and source captures. Local FFmpeg `atempo`
processing preserves pitch; no ElevenLabs request or credential access was needed.
Original artifacts remain unchanged in their separate output folder.

- Added **80** sentence pauses, each 0.25 seconds beyond the existing narration gaps.
- Added **16** transition increments of 0.1 seconds: thirteen chapter transitions and
  three cuts within the toolbox overview. No transition increment follows the final chapter.
- Toolbox cuts now fall after the relevant complete sentences instead of equal-duration
  quarters. Its four scene durations and all caption timings were rebuilt.
- Applied five-millisecond fades at pause edges to avoid abrupt waveform discontinuities.
  No samples were removed. All inserted silence spans and their zero-level edges were verified.
- Measured tempo stretch per chapter was 1.10978–1.11095, consistent with the requested
  90% playback speed (ideal stretch 1.11111; minor FFmpeg endpoint variation).
- Resulting audio timeline: approximately **437.58 seconds**, or **7:18**.
- Twelve offline production-tool tests passed, including preservation of timing and
  waveform content outside the fades, added pause lengths, and sentence-boundary handling.
- Ruff and `git diff --check` passed. A rendered toolbox frame was inspected to confirm
  the Figures scene corresponds to its narrated sentence.
- Final MP4 passed a complete audio/video decode. H.264/AAC, 1920×1080, fourteen
  embedded chapters, duration **7:17.66**, 22,462,787 bytes.
- Final SHA-256: `5852e3ebbfe9f61c48bac1007f43cf97f88bca08758d71db0c51ca31c57cf074`.

Reusable pacing code is `scripts/demo_video/pace_demo.py`. The renderer honors its
`pacing-report.json` scene durations. Video, audio, timing sidecars, and render artifacts
remain outside Git; only source code, tests, and documentation are committed.
