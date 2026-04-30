# MeterCapture — Claude Code project guide

PySide6 desktop app that loads a video, lets the user draw a tight ROI on a
meter LCD, and records the recognized digits with timestamps, exportable to
CSV. OCR runs on `rapidocr-onnxruntime` in rec-only mode.

## Run

```
uv run python main.py
```

Reference test asset: `examples/影片辨識測試影片.mp4` (~30 s, 24 fps, 720p).

## Module map

| File | Responsibility |
|---|---|
| `main.py` | `QApplication` entry point. |
| `meter_capture/main_window.py` | UI, playback, capture pipeline, CSV export. |
| `meter_capture/video_view.py` | `QGraphicsView` plus draggable/resizable `RoiItem`. |
| `meter_capture/ocr_worker.py` | RapidOCR `QThread` worker (rec-only). |

## Further reading (read before deep changes)

- `docs/architecture.md` — module map, data flow, threading model, coordinate systems.
- `docs/ocr-investigation.md` — why rec-only beats det+rec on tight LCDs (with empirical sweep). **Read before touching `ocr_worker.py`.**
- `docs/roadmap.md` — current goals and open questions.
- `docs/sessions/` — per-session worklogs.
- `MEMORY.md` — long-lived project knowledge / invariants / known gotchas.

## Architectural rules

- **No torch / no paddle in runtime deps.** Stay on `rapidocr-onnxruntime`.
- **OCR runs on its own `QThread`.** Never call the recognizer on the GUI thread.
- **ROI lives in scene (frame) coordinates.** Rotation/flip transforms the FRAME, not the ROI — clear the ROI on orientation change.
- **Rec-only OCR (`use_det=False, use_cls=False`).** The user already supplies a tight ROI, so we skip DBNet detection. Don't add CLAHE / Otsu / adaptive-threshold — they fragment 7-segment strokes (verified empirically).

## Devlog rules — read before shipping code

The running developer log lives at `DEVLOG.md`. Every session that ships code
MUST append an entry. Other Claude Code instances opening this repo: follow
this format exactly.

```
## YYYY-MM-DD — short title (author/handle)

**What:** 1–3 bullets of what changed.
**Why:** the user-facing motivation in one sentence.
**Verified:** how you confirmed it works (smoke run, table contents, video tested, etc.).
**Files:** list of paths touched.
**PR/commit:** `#NN` or commit short SHA, when known.
```

Rules:
1. One entry per shipped change. For non-owners that means one entry per merged PR. For the owner pushing directly, one entry per pushed commit-set.
2. Append-only. If a past entry was wrong, write a corrective entry; do not edit history.
3. Newest entry first, directly under the `# Devlog` heading.
4. Keep it terse (target < 12 lines). Long detail belongs in the PR description or commit message.
5. Skip the log for: typo fixes, comment-only edits, devlog edits themselves, dependency-lock-only updates, formatting-only diffs.
6. Mention the affected user-facing feature (UI control, OCR pipeline, etc.) so the log is grep-able.
7. Call out explicitly under **What:** any: dependency bump, public function signature change, default-behaviour change.

## PR workflow

- **Non-owners:** branch → PR → review → merge. `main` is protected — direct pushes are blocked.
- **Owner (`@LostSunset`):** may push to `main` directly. Still updates `DEVLOG.md`.
- PR template is `.github/PULL_REQUEST_TEMPLATE.md`. Don't merge with the devlog checkbox unticked.
