# MeterCapture

PySide6 desktop tool that loads a video, lets you draw a tight ROI on a meter
LCD, and records the recognized digits with frame-accurate timestamps —
exportable to CSV.

OCR runs on `rapidocr-onnxruntime` in **rec-only** mode (skips DBNet text
detection because the user already supplies a tight ROI), so it works
reliably on small 7-segment crops where the default detector starves.

![Status](https://img.shields.io/badge/status-v0.1.0-blue) ![Python](https://img.shields.io/badge/python-3.11+-blue) ![PySide6](https://img.shields.io/badge/UI-PySide6-41cd52)

## Features

- Drag-and-drop a video file (or open via dialog)
- Play / pause / scrub with a frame slider; live FPS readout
- Rotate (-180° … +180°, 0.5° steps) + horizontal/vertical flip
- Draw a red ROI; move it, resize via 8 corner/edge handles
- Auto-record: hit `開始記錄`, the video plays itself and OCRs every N frames
- One-click clear and CSV export (UTF-8 BOM)
- Optional anchor: pair the in-video timestamp with a real-world start time

## Quick start

```bash
# Requires uv (https://docs.astral.sh/uv/) and Python 3.11+
git clone https://github.com/LostSunset/MeterCapture.git
cd MeterCapture
uv sync
uv run python main.py
```

A test asset ships at `examples/影片辨識測試影片.mp4` (~30 s, 24 fps, 720p).

## Output (CSV)

| frame_index | video_time | video_time_sec | real_time | number | raw_text | confidence |
|---|---|---|---|---|---|---|
| 0 | 00:00:00.000 | 0.000 | 2026-04-30T09:30:00.000 | 329 | 329 | 0.9767 |

## Project layout

| Path | Purpose |
|---|---|
| `main.py` | `QApplication` entry point |
| `meter_capture/main_window.py` | UI, playback, capture pipeline, CSV export |
| `meter_capture/video_view.py` | `QGraphicsView` + draggable/resizable `RoiItem` |
| `meter_capture/ocr_worker.py` | RapidOCR `QThread` worker (rec-only) |
| `examples/` | Reference test video |
| `docs/` | Architecture, OCR investigation, session logs, roadmap |
| `CLAUDE.md` | Guide for Claude Code contributors (read first) |
| `DEVLOG.md` | Append-only developer log |

## Documentation

- [Architecture](docs/architecture.md) — module map, threading model, coordinate system
- [OCR investigation](docs/ocr-investigation.md) — why rec-only beats det+rec on LCDs, dispatch-team findings
- [Roadmap](docs/roadmap.md) — current goals and open questions
- [Session logs](docs/sessions/) — per-session worklogs

## Contributing

`main` is protected: non-owners must open a PR (1 approval required). The
repository owner (`@LostSunset`) can push to `main` directly.

Read `CLAUDE.md` first — it documents the **devlog rules** that every shipped
change must follow, including a strict format for `DEVLOG.md` entries so that
multiple Claude Code sessions across contributors leave a consistent log.

PRs should follow `.github/PULL_REQUEST_TEMPLATE.md` and tick the devlog
checkbox before merge.

## License

TBD — add when chosen.
