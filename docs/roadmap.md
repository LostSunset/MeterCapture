# Roadmap

## Goals

1. **Reliable LCD reading** — primary objective. Achieved at 0.97-1.00
   confidence on the reference video using rec-only OCR.
2. **Frame-accurate timestamps** — every captured row is anchored to a
   frame index so the timing is reproducible across re-runs.
3. **Zero-config OCR backend** — pure ONNX, no torch, no system Tesseract
   binary. Stays simple to install for collaborators.
4. **Maintainable Claude-Code-friendly workflow** — every contributor's
   Claude session leaves a consistent `DEVLOG.md` entry; project-wide
   conventions live in `CLAUDE.md`.

## Open questions

- **Decimal-point detection.** Rec-only outputs digits cleanly but PP-OCRv4
  sometimes drops `.` on small fonts. Acceptable so far for integer LCDs
  but will need a blob-based postprocess for decimal meters.
- **Drift across long videos.** No empirical study yet of recognition
  stability over hour-scale clips with shifting backlight.
- **Multiple ROIs.** Current UI supports one ROI. Real meters often have
  two readings (e.g., kWh + voltage). Adding a list of ROIs with per-ROI
  CSV columns is a clean extension but doubles the OCR thread load.

## Future ideas

| Idea | Effort | Pay-off |
|---|---|---|
| English/digits-only PP-OCRv4 rec model swap | small | small accuracy bump |
| 7-segment fine-tuned rec checkpoint | medium | larger accuracy bump |
| Confidence-fallback to `ssocr` | small | robustness on hard frames |
| Multi-frame majority vote (N=3-5) | small | smooths video noise |
| Multiple ROIs with per-ROI columns | medium | covers multi-reading meters |
| Preview overlay of recognized text on the frame | small | better UX validation |
| Headless / batch mode (`uv run python main.py --headless ...`) | medium | CI-friendly |
| Auto-rotate suggestion via `cv2.minAreaRect` on the frame | small | one-click leveling |

## Non-goals (for now)

- Real-time RTSP / camera ingest — file-based workflow is enough.
- Cloud OCR services — defeats the no-config goal.
- Mobile/tablet UI — desktop-only.
