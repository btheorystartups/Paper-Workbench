# Natural narration revision — 2026-09-12

The user reported audible background changes around sentence endings and requested
a fresh ElevenLabs take, somewhat more enthusiasm, and approximately the same pace.

Generated one fresh continuous take using the same Brian clone, multilingual v2,
seed 20260912, stability 0.50, similarity 0.55, style 0.45, speaker boost off,
and native speed 0.88. Only the existing synthetic tutorial text was sent to ElevenLabs.
The source take lasted 428.640 seconds, already matching the previous 428.587-second
timeline. The tempo factor was unity; its natural sentence pauses were retained.

This edition removes sentence-level digital silence insertion, noise gating, and
adaptive noise reduction. These were possible contributors to the reported acoustic
changes, not an independently established sole cause. Only a fixed -0.9 dB gain is
applied, leaving peak headroom without changing gain between sentences. The renderer
uses the continuous PCM master for one final AAC encode, rather than joining chapter
audio encodes. Visual chapter cuts do not splice the final soundtrack.

All 55 existing UI callouts and 90 caption cues were retimed from the fresh character
alignment. No new browser capture or research database access was needed.

Verification: fourteen offline production-tool tests passed; Ruff and diff checks
passed. Full MP4 audio/video decoding passed. Final duration is 7:08.69, 1080p/30 fps,
H.264/AAC, with fourteen chapter markers. Encoded audio has -2.1 dBFS sample peak and
-23.6 dBFS mean volume. The native delivery and dynamic range are preserved; this
edition may play quieter than the earlier loudness-normalized version.

`verify_guided.py` checks all rendered highlight outlines and requires concatenated
chapter PCM to equal the uninterrupted master exactly. The local output folder is
`output/paper-workbench-demo-brian-natural-20260912`. Generated verification reports
contain the media checksum and frame contact sheet. Previous editions are preserved.
Code and documentation are versioned; generated media and voice identifiers stay local.

These checks verify continuity and encoding, not perceived enthusiasm or absence of
all artifacts intrinsic to the synthesized voice. No independent listening or speech
recognition assessment is claimed.
