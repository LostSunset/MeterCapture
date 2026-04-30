"""OCR worker thread using RapidOCR (ONNX, no torch).

Rec-only mode: the user already draws a tight ROI, so we skip DBNet detection
and feed the whole crop straight into the recognizer. Empirically this lifts
confidence from ~0% to >0.97 on small 7-segment LCD crops, and runs ~20x faster.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np
from PySide6.QtCore import QObject, QThread, Signal, Slot


@dataclass
class OcrJob:
    frame_index: int
    video_time_sec: float
    image: np.ndarray  # BGR cropped ROI


@dataclass
class OcrResult:
    frame_index: int
    video_time_sec: float
    text: str
    number: str
    confidence: float


class OcrWorker(QObject):
    result_ready = Signal(object)
    error = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._reader = None

    @Slot()
    def initialize(self) -> None:
        try:
            from rapidocr_onnxruntime import RapidOCR

            self._reader = RapidOCR()
        except Exception as exc:  # noqa: BLE001
            self.error.emit(f"OCR init failed: {exc}")

    @Slot(object)
    def run_job(self, job: OcrJob) -> None:
        if self._reader is None:
            self.initialize()
            if self._reader is None:
                return
        try:
            img = job.image
            if img is None or img.size == 0:
                return
            img = self._preprocess(img)
            # Rec-only: treat the whole ROI as a single text line, skip detection.
            result, _ = self._reader(
                img, use_det=False, use_cls=False, use_rec=True
            )
            if not result:
                return
            texts: list[str] = []
            confs: list[float] = []
            for item in result:
                # rec-only return shape: [[text, score], ...]
                if len(item) >= 2:
                    texts.append(str(item[0]))
                    confs.append(float(item[1]))
            joined = " ".join(texts).strip()
            if not joined:
                return
            number = self._extract_number(joined)
            avg_conf = float(np.mean(confs)) if confs else 0.0
            self.result_ready.emit(
                OcrResult(
                    frame_index=job.frame_index,
                    video_time_sec=job.video_time_sec,
                    text=joined,
                    number=number,
                    confidence=avg_conf,
                )
            )
        except Exception as exc:  # noqa: BLE001
            self.error.emit(f"OCR error: {exc}")

    @staticmethod
    def _preprocess(img: np.ndarray) -> np.ndarray:
        # Empirically: CLAHE / Otsu / adaptive-threshold all HURT thin 7-segment
        # strokes. Modest cubic upscale is the only step that consistently helps.
        import cv2

        h, w = img.shape[:2]
        short = min(h, w)
        if short < 64:
            scale = 64.0 / float(short)
            img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        return img

    @staticmethod
    def _extract_number(text: str) -> str:
        m = re.search(r"-?\d+(?:\.\d+)?", text.replace(",", "."))
        return m.group(0) if m else ""


class OcrController(QObject):
    """Owns the OCR thread and forwards jobs to it."""

    submit_job = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread = QThread()
        self._thread.setObjectName("OcrThread")
        self._worker = OcrWorker()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.initialize)
        self.submit_job.connect(self._worker.run_job)
        self._thread.start()

    @property
    def worker(self) -> OcrWorker:
        return self._worker

    def shutdown(self) -> None:
        self._thread.quit()
        self._thread.wait(2000)
