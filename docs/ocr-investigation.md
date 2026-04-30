# OCR investigation — why rec-only beats det+rec

## TL;DR

- We dispatched three parallel research agents on 2026-04-30 to diagnose poor
  recognition on tight LCD ROIs.
- All three converged: **PP-OCRv4's DBNet text detector starves on tight
  crops** — it expects natural-scene padding around text. With no padding,
  detection returns either nothing or fragmented partial boxes
  (`"WIND 29 M"` instead of `"329"`).
- Skipping detection (`use_det=False, use_cls=False, use_rec=True`) feeds the
  whole ROI directly into the recognizer. Result: confidence rises from ~0
  to **0.97-1.00**, latency drops from **~870 ms to ~30 ms**.
- Heavy preprocessing (CLAHE, Otsu, adaptive threshold, morphological close)
  was empirically **harmful** on 7-segment LCDs — it fragments thin segment
  strokes. We removed it.

## Empirical sweep (test video frame at ~7 s, true reading "291")

| Rank | Method | use_det | conf | latency | text | OK |
|---:|---|---:|---:|---:|---|:---:|
| 1 | rec-only + 4× upscale | 0 | 0.977 | 28 ms | `'291'` | ✅ |
| 2 | rec-only (raw crop) | 0 | 0.976 | 37 ms | `'291'` | ✅ |
| 3 | det+rec, rotated -2° | 1 | 0.995 | 911 ms | `'WIND 29 M'` | ❌ |
| 4 | det+rec default | 1 | 0.993 | 871 ms | `'WIND 29 M'` | ❌ |
| 5 | det+rec + white pad 30 px | 1 | 0.990 | 1791 ms | `'WIND 29'` | ❌ |
| – | Otsu / adaptive / 8× upscale | – | – | – | `''` / junk | ❌ |

The "WIND" / "M" tokens are noise pulled from elsewhere in the un-tightened
crop — det+rec finds them with high confidence but mis-segments the actual
"3" in "329" and drops it into border-replicate padding.

## RapidOCR API used

```python
from rapidocr_onnxruntime import RapidOCR
reader = RapidOCR()

# Rec-only: skip DBNet; treat the whole crop as one text line.
result, _ = reader(crop_bgr, use_det=False, use_cls=False, use_rec=True)
# result -> [[text, score], ...]   e.g. [['329', 0.9997]]
```

Notable kwargs:
- `box_thresh`, `unclip_ratio`, `text_score`, `return_word_box` are accepted
  per-call (det+rec mode only).
- Constructor-only kwargs (`det_thresh`, `rec_img_shape`, `rec_keys_path`,
  `width_height_ratio`, …) require restarting the worker to change.
- No allowlist parameter — apply a regex post-filter
  (`re.search(r"-?\d+(?:\.\d+)?", text)`) for digit-only output.

## Preprocessing rules of thumb

Stick to:
- Modest cubic upscale to short side ≥ 64 px (rec model internally rescales
  to height 48; bigger inputs to that resize improve quality slightly).
- That's it.

Avoid on 7-segment LCDs:
- CLAHE — empirically a no-op or harmful on already-high-contrast LCDs.
- Otsu / adaptive thresholding — fragments thin segment strokes.
- Heavy morphological close — bridges adjacent digits.
- 8× or larger upscale — softens edges past what bilinear-equivalent rec
  internal resize wants.

## Open questions / future work

- Custom rec model. PaddleOCR publishes English/digits-only PP-OCRv4 rec
  weights and a 7-seg fine-tune is feasible. Would swap in via
  `RapidOCR(rec_model_path=…, rec_keys_path=…)`.
- Confidence-fallback to `ssocr` for very low-conf frames (<0.6).
- Multi-frame voting: sample N consecutive frames, majority-vote the digit
  string. Cheap and effective for video noise.

## Audit trail

Three subagents in parallel, all on 2026-04-30:
- API researcher — confirmed `use_det=False` signature, return shapes, model
  swap mechanism. Source: `.venv/Lib/site-packages/rapidocr_onnxruntime/main.py`.
- Best-practices researcher — recommended option (1) keep RapidOCR + better
  preprocess; option (2) ssocr fallback if needed.
- Empirical sweep — extracted frames from the test video, ran 14
  preprocess/OCR variants, confirmed rec-only as winner, also surprised:
  the user's ~9° rotation was unnecessary (LCD already near-horizontal).

Sweep artifacts under `examples/_*` (gitignored, kept locally for inspection).
