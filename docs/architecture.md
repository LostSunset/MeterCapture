# Architecture

## High-level data flow

```
        ┌──────────────────┐    cv2 frame     ┌──────────────────┐
file →  │  VideoCapture    │ ───────────────► │  _apply_orient   │
        │  (cv2)           │   (BGR ndarray)  │  rotate + flip   │
        └──────────────────┘                  └────────┬─────────┘
                                                       │
                                          rotated frame│
                                                       ▼
                          ┌────────────────────────────────────────┐
                          │  VideoView (QGraphicsView + RoiItem)   │
                          │  display + ROI in scene coords         │
                          └────────────────────┬───────────────────┘
                                               │ ROI rect (clamped)
                                               ▼
                          ┌────────────────────────────────────────┐
   QThread ◄── Signal ── │  MainWindow                              │
                          │  • playback timer (1/fps ms)            │
                          │  • frame-interval gating               │
                          │  • crops ROI → enqueues OcrJob          │
                          └────────────────────┬───────────────────┘
                                               │ submit_job
                                               ▼
                          ┌────────────────────────────────────────┐
                          │  OcrWorker (own QThread)                │
                          │  rapidocr_onnxruntime, rec-only         │
                          │     ocr(crop, use_det=False,            │
                          │         use_cls=False, use_rec=True)    │
                          └────────────────────┬───────────────────┘
                                               │ result_ready Signal
                                               ▼
                          ┌────────────────────────────────────────┐
                          │  MainWindow._on_ocr_result              │
                          │    → table row + Capture[]              │
                          │    → 輸出 CSV button                    │
                          └────────────────────────────────────────┘
```

## Module responsibilities

### `main.py`
Trivial. Boots `QApplication`, instantiates `MainWindow`, calls `app.exec()`.

### `meter_capture/main_window.py`
Owns playback (`QTimer` driven at `1000/fps` ms), the recordings list, the
results table, the orientation state, and the OCR controller. Every
state-changing UI event flows here.

Transport timer ticks call `_tick`, which:
1. reads next frame from `cv2.VideoCapture` (no re-seek — naturally advances)
2. applies orientation (`_apply_orientation`)
3. updates the `VideoView` pixmap and the time/slider labels
4. if `_capturing`, calls `_maybe_record_now` to gate by frame interval

### `meter_capture/video_view.py`
`QGraphicsView` subclass with one pixmap item plus an optional `RoiItem`.
Draw mode: rubber-band-style drag creates a new `RoiItem`. The item exposes
`frame_rect()` returning ROI in **frame (scene) coordinates** so the main
window can clamp and crop directly off the BGR ndarray.

### `meter_capture/ocr_worker.py`
`OcrController` owns a `QThread`; `OcrWorker` lives on it. Jobs are dispatched
via signal, results returned via `result_ready`. OCR uses RapidOCR's rec-only
mode — see `docs/ocr-investigation.md` for the rationale.

## Threading model

| Thread | Owns |
|---|---|
| GUI (main) | All `QWidget` instances, `cv2.VideoCapture`, the frame buffer, the timer |
| OCR worker (`QThread`) | RapidOCR session, ONNX runtimes |

Communication is one-way Signal/Slot:
- GUI → worker: `submit_job` carrying an `OcrJob` (frame copy + index + time)
- Worker → GUI: `result_ready` carrying an `OcrResult`

The frame data is copied (`crop = frame[y1:y2, x1:x2].copy()`) before
enqueuing, so the worker can hold the buffer without GUI-thread aliasing.

## Coordinate systems

- **Frame coords:** the rotated BGR ndarray dimensions (e.g., 720×1280 after
  90°). This is the "scene" coordinate space inside the `QGraphicsView`.
- **View coords:** widget pixels — used only by mouse events; mapped via
  `mapToScene` immediately.
- **ROI invariants:** `RoiItem` lives in the scene coord system; cropping
  clamps to `(0, 0)` and `(frame_w, frame_h)`.

When the user changes rotation/flip, `MainWindow` calls
`self.view.clear_roi()` to drop any stale ROI before refreshing the frame —
the previous ROI's coordinates no longer mean anything.

## Why no `QMediaPlayer`?

`QMediaPlayer` doesn't expose raw frames easily. We need pixel-level access
for OCR cropping, so `cv2.VideoCapture` driven by `QTimer` is the simplest
correct path.

## Why no torch / paddle?

The default `rapidocr-onnxruntime` ships ONNX models with no torch/paddle
dependency, ~150 MB total. EasyOCR / PaddleOCR each pull in 1.5+ GB of GPU
runtimes for marginal gains on this task. Not worth it.
