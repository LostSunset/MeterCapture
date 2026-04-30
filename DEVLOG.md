# Devlog

Append-only log of shipped changes. See `CLAUDE.md` for rules.

## 2026-04-30 — Initial app: video → ROI → OCR → CSV (@LostSunset)

**What:**
- PySide6 main window with cv2-based playback (drag-drop or file picker), seek slider, play/pause/stop, FPS readout.
- Draggable + resizable red ROI overlay (8-handle resize) on `QGraphicsView`.
- Rotation `-180°…+180°` (0.5° step) plus H/V flip applied to the displayed frame; ROI clears on orientation change.
- Frame-interval recording: `開始記錄` auto-plays the video and OCRs every N frames; auto-stops at end-of-video. `清除紀錄` with confirm dialog. `輸出 CSV` with UTF-8 BOM.
- OCR via `rapidocr-onnxruntime` in rec-only mode (`use_det=False, use_cls=False`); skips DBNet detection because the user already draws a tight ROI. ~30 ms/job vs ~870 ms with det+rec; CLAHE/Otsu/adaptive-threshold removed (empirically harmful on 7-seg LCDs).

**Why:** Capture LCD meter readings from video with frame-accurate timestamps, exportable to CSV — det+rec mode was failing tight LCD crops at 0 confidence.

**Verified:**
- `examples/影片辨識測試影片.mp4` (24 fps, 30.875 s, 1280×720): rec-only reads "291" / "303" / "318" / "329" at 0.97–1.00 confidence across the timeline.
- Rotation paths: 0° / 90° / 180° / 270° / -45° all produce correctly sized frames; ROI clears on rotation change.
- Frame interval: at N=30 the recorder fires at frame 0, 30, 60, … and skips at 15 (smoke test).

**Files:**
- `pyproject.toml` (PySide6, opencv-python, numpy, rapidocr-onnxruntime, Python 3.11)
- `main.py`
- `meter_capture/{__init__,main_window,video_view,ocr_worker}.py`
- `.gitignore`, `CLAUDE.md`, `DEVLOG.md`, `.github/PULL_REQUEST_TEMPLATE.md`

**PR/commit:** initial commit
