# Project memory

Long-lived knowledge about MeterCapture — meant for AI assistants and
new contributors who want the "why" without re-deriving it.

## Core invariants

- **Rec-only OCR is the default.** Do not switch to det+rec on tight LCD
  crops; it starves and returns garbage. See `docs/ocr-investigation.md`.
- **No torch / no paddle.** Stay on `rapidocr-onnxruntime`. Adding heavy
  deep-learning runtimes for marginal gains is a non-starter.
- **OCR runs on its own `QThread`.** The GUI thread must never block on
  OCR.
- **Frame-interval recording, not time-interval.** Sampling cadence
  follows the user's `每 N 幀` setting because it's reproducible across
  re-runs and aligns with how OCR is gated.
- **Rotation/flip transforms the FRAME, not the ROI.** Clear the ROI on
  any orientation change — old coordinates are meaningless.

## Empirical lessons (do not relearn)

- CLAHE on Y channel: no-op on this LCD, sometimes harmful.
- Otsu / adaptive threshold: fragments thin 7-segment strokes — harmful.
- Morphological close: bridges adjacent digits — harmful.
- 8× upscale: softens segment edges past what the recognizer wants.
- Modest 2-4× cubic upscale: marginally helpful when short side < 64 px.
- White-padding the ROI: helps det+rec but hurts rec-only — irrelevant
  in our default pipeline.

## Test asset

- `examples/影片辨識測試影片.mp4` — 30.875 s, 24 fps, 1280×720, ~9.6 MB.
- Reference reading at frame 0: `"303"`. Drifts to `"291"`, `"316"`,
  `"329"` over the clip.
- Rotation: ≈0° (LCD is already near-horizontal). Earlier sessions
  rotated ~9° unnecessarily.

## Workflow facts

- `main` branch protected; non-owners need PR with 1 approval. Owner
  (`@LostSunset`) bypasses via `enforce_admins=false`.
- `DEVLOG.md` is append-only; rules live in `CLAUDE.md`.
- Dev sweep artifacts go under `examples/_*` (gitignored).

## Known gotchas

- RapidOCR has no allowlist parameter. Apply
  `re.search(r"-?\d+(?:\.\d+)?", text)` to filter to digits.
- Decimal points are sometimes dropped on small fonts. Plan: blob-based
  decimal detection if/when a decimal meter shows up.
- `cv2.VideoCapture.set(CAP_PROP_POS_FRAMES, …)` only re-seeks when the
  target differs from the current cursor; `_tick` exploits this for
  smooth natural-advance playback.
