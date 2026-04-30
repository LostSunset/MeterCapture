"""Main window: video player + ROI + OCR + CSV export."""
from __future__ import annotations

import csv
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path

import cv2
import numpy as np
from PySide6.QtCore import QRectF, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QDateTimeEdit,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QStatusBar,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import QDateTime

from .ocr_worker import OcrController, OcrJob, OcrResult
from .video_view import VideoView


def _fmt_time(seconds: float) -> str:
    if seconds is None or seconds < 0:
        seconds = 0.0
    ms = int(round((seconds - int(seconds)) * 1000))
    s = int(seconds) % 60
    m = (int(seconds) // 60) % 60
    h = int(seconds) // 3600
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


@dataclass
class Capture:
    frame_index: int
    video_time_sec: float
    video_time_str: str
    real_time_iso: str
    text: str
    number: str
    confidence: float


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Meter Capture - 影片數字辨識")
        self.resize(1280, 820)
        self.setAcceptDrops(True)

        self._cap: cv2.VideoCapture | None = None
        self._fps: float = 30.0
        self._frame_count: int = 0
        self._duration_sec: float = 0.0
        self._current_frame_idx: int = 0
        self._current_frame: np.ndarray | None = None  # rotated frame shown in view
        self._raw_frame: np.ndarray | None = None  # un-rotated frame from cv2
        self._video_path: Path | None = None
        self._captures: list[Capture] = []
        self._capturing: bool = False
        self._last_capture_frame: int = -1
        self._rotation: float = 0.0
        self._flip_h: bool = False
        self._flip_v: bool = False

        self._ocr = OcrController(self)
        self._ocr.worker.result_ready.connect(self._on_ocr_result)
        self._ocr.worker.error.connect(self._on_ocr_error)

        # ----- central layout
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        self.view = VideoView()
        root.addWidget(self.view, stretch=3)

        # ----- transport row
        transport = QHBoxLayout()
        self.btn_play = QPushButton(self.style().standardIcon(QStyle.SP_MediaPlay), "")
        self.btn_play.setToolTip("Play / Pause (Space)")
        self.btn_play.clicked.connect(self.toggle_play)

        self.btn_stop = QPushButton(self.style().standardIcon(QStyle.SP_MediaStop), "")
        self.btn_stop.setToolTip("Stop")
        self.btn_stop.clicked.connect(self.stop)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 0)
        self.slider.sliderMoved.connect(self._on_slider_moved)
        self.slider.sliderReleased.connect(self._on_slider_released)

        self.lbl_time = QLabel("00:00:00.000 / 00:00:00.000")
        self.lbl_time.setMinimumWidth(220)

        self.lbl_fps = QLabel("FPS: --")
        self.lbl_fps.setMinimumWidth(110)
        self.lbl_fps.setToolTip("影片每秒幀數 (frames per second)")
        self.lbl_fps.setStyleSheet(
            "QLabel { padding: 2px 8px; border: 1px solid #888; border-radius: 4px; }"
        )

        transport.addWidget(self.btn_play)
        transport.addWidget(self.btn_stop)
        transport.addWidget(self.slider, stretch=1)
        transport.addWidget(self.lbl_time)
        transport.addWidget(self.lbl_fps)
        root.addLayout(transport)

        # ----- capture row
        capture_row = QHBoxLayout()
        self.btn_open = QPushButton("開啟影片")
        self.btn_open.clicked.connect(self.open_video_dialog)

        self.btn_add_roi = QPushButton("新增辨識框")
        self.btn_add_roi.setCheckable(True)
        self.btn_add_roi.toggled.connect(self.view.set_draw_mode)

        self.btn_clear_roi = QPushButton("清除辨識框")
        self.btn_clear_roi.clicked.connect(self.view.clear_roi)

        self.btn_capture_now = QPushButton("立即辨識")
        self.btn_capture_now.clicked.connect(self._capture_now)

        self.btn_record = QPushButton("開始記錄")
        self.btn_record.setCheckable(True)
        self.btn_record.toggled.connect(self._toggle_recording)

        self.spin_interval = QSpinBox()
        self.spin_interval.setRange(1, 100000)
        self.spin_interval.setValue(30)
        self.spin_interval.setSingleStep(1)
        self.spin_interval.setSuffix(" 幀")
        self.spin_interval.setToolTip("每 N 幀記錄一次（按住 Shift 拖滑鼠可快速調整）")

        self.btn_clear_records = QPushButton("清除紀錄")
        self.btn_clear_records.clicked.connect(self.clear_records)

        self.btn_export = QPushButton("輸出 CSV")
        self.btn_export.clicked.connect(self.export_csv)

        capture_row.addWidget(self.btn_open)
        capture_row.addSpacing(12)
        capture_row.addWidget(self.btn_add_roi)
        capture_row.addWidget(self.btn_clear_roi)
        capture_row.addSpacing(12)
        capture_row.addWidget(QLabel("每"))
        capture_row.addWidget(self.spin_interval)
        capture_row.addWidget(QLabel("記錄一次"))
        capture_row.addWidget(self.btn_capture_now)
        capture_row.addWidget(self.btn_record)
        capture_row.addStretch(1)
        capture_row.addWidget(self.btn_clear_records)
        capture_row.addWidget(self.btn_export)
        root.addLayout(capture_row)

        # ----- rotation / flip row
        rot_row = QHBoxLayout()
        rot_row.addWidget(QLabel("旋轉:"))
        self.spin_rot = QDoubleSpinBox()
        self.spin_rot.setRange(-180.0, 180.0)
        self.spin_rot.setSingleStep(0.5)
        self.spin_rot.setDecimals(1)
        self.spin_rot.setValue(0.0)
        self.spin_rot.setSuffix(" °")
        self.spin_rot.valueChanged.connect(self._on_rotation_changed)
        rot_row.addWidget(self.spin_rot)

        self.slider_rot = QSlider(Qt.Horizontal)
        self.slider_rot.setRange(-1800, 1800)  # 0.1° steps
        self.slider_rot.setValue(0)
        self.slider_rot.valueChanged.connect(
            lambda v: self.spin_rot.setValue(v / 10.0)
        )
        rot_row.addWidget(self.slider_rot, stretch=1)

        self.btn_rot_ccw = QPushButton("⟲ -90°")
        self.btn_rot_ccw.clicked.connect(lambda: self._nudge_rotation(-90))
        self.btn_rot_cw = QPushButton("⟳ +90°")
        self.btn_rot_cw.clicked.connect(lambda: self._nudge_rotation(+90))
        self.btn_rot_reset = QPushButton("重設")
        self.btn_rot_reset.clicked.connect(lambda: self.spin_rot.setValue(0.0))
        rot_row.addWidget(self.btn_rot_ccw)
        rot_row.addWidget(self.btn_rot_cw)
        rot_row.addWidget(self.btn_rot_reset)

        self.chk_flip_h = QCheckBox("水平翻轉")
        self.chk_flip_h.toggled.connect(self._on_flip_h)
        self.chk_flip_v = QCheckBox("垂直翻轉")
        self.chk_flip_v.toggled.connect(self._on_flip_v)
        rot_row.addWidget(self.chk_flip_h)
        rot_row.addWidget(self.chk_flip_v)
        root.addLayout(rot_row)

        # ----- start time row (optional anchor for "real-world" timestamp)
        time_row = QHBoxLayout()
        self.chk_use_start = QCheckBox("使用影片起始時間")
        self.chk_use_start.setChecked(False)
        self.dt_start = QDateTimeEdit(QDateTime.currentDateTime())
        self.dt_start.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.dt_start.setCalendarPopup(True)
        time_row.addWidget(self.chk_use_start)
        time_row.addWidget(self.dt_start)
        time_row.addStretch(1)
        root.addLayout(time_row)

        # ----- results table
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["影片時間", "真實時間", "數字", "原始文字", "信心度"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        root.addWidget(self.table, stretch=2)

        # ----- status bar
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("拖曳影片到視窗，或點『開啟影片』")

        # ----- playback timer
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

        # ----- shortcuts
        play_act = QAction(self)
        play_act.setShortcut(QKeySequence(Qt.Key_Space))
        play_act.triggered.connect(self.toggle_play)
        self.addAction(play_act)

    # ------------------------------------------------------------- drag & drop
    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith(
                    (".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".wmv", ".flv")
                ):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event) -> None:
        urls = event.mimeData().urls()
        if not urls:
            return
        path = Path(urls[0].toLocalFile())
        if path.exists():
            self.load_video(path)
            event.acceptProposedAction()

    # ------------------------------------------------------------- video I/O
    def open_video_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "選擇影片",
            str(self._video_path.parent if self._video_path else Path.cwd()),
            "Video files (*.mp4 *.mov *.avi *.mkv *.webm *.m4v *.wmv *.flv);;All files (*.*)",
        )
        if path:
            self.load_video(Path(path))

    def load_video(self, path: Path) -> None:
        self.stop()
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            QMessageBox.critical(self, "錯誤", f"無法開啟影片:\n{path}")
            return
        self._cap = cap
        self._video_path = path
        self._fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        if self._fps <= 0 or self._fps > 240:
            self._fps = 30.0
        self._frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        self._duration_sec = self._frame_count / self._fps if self._fps > 0 else 0
        self._current_frame_idx = 0
        self._last_capture_time = -1.0
        self.slider.blockSignals(True)
        self.slider.setRange(0, max(0, self._frame_count - 1))
        self.slider.setValue(0)
        self.slider.blockSignals(False)

        self._read_frame_at(0)
        self._update_time_label()
        self.lbl_fps.setText(f"FPS: {self._fps:.2f}")
        self.lbl_fps.setToolTip(
            f"FPS: {self._fps:.4f}\n總幀數: {self._frame_count}\n時長: {_fmt_time(self._duration_sec)}"
        )
        self.setWindowTitle(f"Meter Capture - {path.name}")
        self.statusBar().showMessage(
            f"已載入 {path.name}  |  {self._frame_count} 幀  |  {self._fps:.2f} fps  |  時長 {_fmt_time(self._duration_sec)}"
        )

    def _read_frame_at(self, frame_idx: int) -> None:
        if self._cap is None:
            return
        frame_idx = max(0, min(frame_idx, max(0, self._frame_count - 1)))
        # Only re-seek when not naturally advancing
        cur_pos = int(self._cap.get(cv2.CAP_PROP_POS_FRAMES))
        if frame_idx != cur_pos:
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ok, frame = self._cap.read()
        if not ok or frame is None:
            return
        self._raw_frame = frame
        rotated = self._apply_orientation(frame)
        self._current_frame = rotated
        self._current_frame_idx = frame_idx
        self.view.set_frame_bgr(rotated)

    # ------------------------------------------------------------- transport
    def toggle_play(self) -> None:
        if self._cap is None:
            return
        if self._timer.isActive():
            self._timer.stop()
            self.btn_play.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        else:
            interval_ms = max(1, int(round(1000.0 / self._fps)))
            self._timer.start(interval_ms)
            self.btn_play.setIcon(self.style().standardIcon(QStyle.SP_MediaPause))

    def stop(self) -> None:
        self._timer.stop()
        self.btn_play.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        if self._cap is not None:
            self._read_frame_at(0)
            self.slider.setValue(0)
            self._update_time_label()

    def _tick(self) -> None:
        if self._cap is None:
            return
        next_idx = self._current_frame_idx + 1
        if next_idx >= self._frame_count:
            self._timer.stop()
            self.btn_play.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
            if self._capturing:
                self.btn_record.setChecked(False)
                self.statusBar().showMessage("影片播放結束，已停止記錄", 5000)
            return
        # natural read: cap is positioned at next_idx, just read
        ok, frame = self._cap.read()
        if not ok or frame is None:
            self._timer.stop()
            return
        self._raw_frame = frame
        rotated = self._apply_orientation(frame)
        self._current_frame = rotated
        self._current_frame_idx = next_idx
        self.view.set_frame_bgr(rotated)
        if not self.slider.isSliderDown():
            self.slider.blockSignals(True)
            self.slider.setValue(next_idx)
            self.slider.blockSignals(False)
        self._update_time_label()
        if self._capturing:
            self._maybe_record_now()

    def _on_slider_moved(self, value: int) -> None:
        # show the frame while scrubbing
        self._read_frame_at(value)
        self._update_time_label()

    def _on_slider_released(self) -> None:
        self._read_frame_at(self.slider.value())
        self._update_time_label()

    def _update_time_label(self) -> None:
        cur = self._current_frame_idx / self._fps if self._fps > 0 else 0.0
        self.lbl_time.setText(f"{_fmt_time(cur)} / {_fmt_time(self._duration_sec)}")

    # ------------------------------------------------------------- capture
    def _toggle_recording(self, on: bool) -> None:
        self._capturing = on
        self.btn_record.setText("停止記錄" if on else "開始記錄")
        if on:
            if self._cap is None:
                self.statusBar().showMessage("請先載入影片")
                self.btn_record.setChecked(False)
                return
            if self.view.get_roi_rect().isEmpty():
                self.statusBar().showMessage("請先新增辨識框")
                self.btn_record.setChecked(False)
                return
            self._last_capture_frame = -1
            interval = self.spin_interval.value()
            self.statusBar().showMessage(f"記錄中（每 {interval} 幀）")
            # capture the current frame first, then start playback
            self._maybe_record_now(force=True)
            if not self._timer.isActive():
                self.toggle_play()
        else:
            self.statusBar().showMessage("已停止記錄")
            if self._timer.isActive():
                self.toggle_play()

    def _maybe_record_now(self, force: bool = False) -> None:
        if self._cap is None or self._current_frame is None:
            return
        cur_idx = self._current_frame_idx
        if not force:
            interval = max(1, int(self.spin_interval.value()))
            if self._last_capture_frame >= 0 and (cur_idx - self._last_capture_frame) < interval:
                return
        self._last_capture_frame = cur_idx
        cur_t = cur_idx / self._fps if self._fps > 0 else 0.0
        self._submit_ocr_job(self._current_frame, cur_idx, cur_t)

    def _capture_now(self) -> None:
        if self._cap is None or self._current_frame is None:
            QMessageBox.information(self, "提示", "請先載入影片")
            return
        if self.view.get_roi_rect().isEmpty():
            QMessageBox.information(self, "提示", "請先新增辨識框")
            return
        cur_t = self._current_frame_idx / self._fps if self._fps > 0 else 0.0
        self._submit_ocr_job(self._current_frame, self._current_frame_idx, cur_t)

    def _submit_ocr_job(self, frame: np.ndarray, frame_idx: int, video_t: float) -> None:
        roi = self.view.get_roi_rect()
        if roi.isEmpty():
            return
        h, w = frame.shape[:2]
        x1 = int(max(0, min(w - 1, roi.left())))
        y1 = int(max(0, min(h - 1, roi.top())))
        x2 = int(max(0, min(w, roi.right())))
        y2 = int(max(0, min(h, roi.bottom())))
        if x2 - x1 < 4 or y2 - y1 < 4:
            return
        crop = frame[y1:y2, x1:x2].copy()
        self._ocr.submit_job.emit(OcrJob(frame_index=frame_idx, video_time_sec=video_t, image=crop))

    def _on_ocr_result(self, res: OcrResult) -> None:
        real_time = ""
        if self.chk_use_start.isChecked():
            base = self.dt_start.dateTime().toPython()
            ts: datetime = base + timedelta(seconds=res.video_time_sec)
            real_time = ts.isoformat(timespec="milliseconds")
        cap = Capture(
            frame_index=res.frame_index,
            video_time_sec=res.video_time_sec,
            video_time_str=_fmt_time(res.video_time_sec),
            real_time_iso=real_time,
            text=res.text,
            number=res.number,
            confidence=res.confidence,
        )
        self._captures.append(cap)
        self._append_row(cap)

    def _on_ocr_error(self, message: str) -> None:
        self.statusBar().showMessage(message, 5000)

    def _append_row(self, cap: Capture) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        items = [
            cap.video_time_str,
            cap.real_time_iso,
            cap.number,
            cap.text,
            f"{cap.confidence:.2f}",
        ]
        for col, val in enumerate(items):
            it = QTableWidgetItem(val)
            it.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, col, it)
        self.table.scrollToBottom()

    # ------------------------------------------------------------- export
    def clear_records(self) -> None:
        if not self._captures:
            return
        ret = QMessageBox.question(
            self,
            "清除紀錄",
            f"確定要清除 {len(self._captures)} 筆辨識紀錄？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ret != QMessageBox.Yes:
            return
        self._captures.clear()
        self.table.setRowCount(0)
        self._last_capture_frame = -1
        self.statusBar().showMessage("已清除紀錄", 3000)

    def export_csv(self) -> None:
        if not self._captures:
            QMessageBox.information(self, "提示", "尚未有任何辨識結果")
            return
        default_name = (
            (self._video_path.stem if self._video_path else "captures") + "_captures.csv"
        )
        path, _ = QFileDialog.getSaveFileName(
            self, "輸出 CSV", str(Path.cwd() / default_name), "CSV (*.csv)"
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(
                ["frame_index", "video_time", "video_time_sec", "real_time", "number", "raw_text", "confidence"]
            )
            for c in self._captures:
                writer.writerow(
                    [
                        c.frame_index,
                        c.video_time_str,
                        f"{c.video_time_sec:.3f}",
                        c.real_time_iso,
                        c.number,
                        c.text,
                        f"{c.confidence:.4f}",
                    ]
                )
        self.statusBar().showMessage(f"已輸出: {path}", 5000)

    # ------------------------------------------------------------- orientation
    def _apply_orientation(self, frame: np.ndarray) -> np.ndarray:
        if frame is None:
            return frame
        out = frame
        if self._flip_h:
            out = cv2.flip(out, 1)
        if self._flip_v:
            out = cv2.flip(out, 0)
        ang = self._rotation % 360
        if ang == 0:
            return out
        if ang == 90:
            return cv2.rotate(out, cv2.ROTATE_90_CLOCKWISE)
        if ang == 180:
            return cv2.rotate(out, cv2.ROTATE_180)
        if ang == 270:
            return cv2.rotate(out, cv2.ROTATE_90_COUNTERCLOCKWISE)
        h, w = out.shape[:2]
        M = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), self._rotation, 1.0)
        cos_v = abs(M[0, 0])
        sin_v = abs(M[0, 1])
        new_w = int(round(h * sin_v + w * cos_v))
        new_h = int(round(h * cos_v + w * sin_v))
        M[0, 2] += (new_w - w) / 2.0
        M[1, 2] += (new_h - h) / 2.0
        return cv2.warpAffine(
            out, M, (new_w, new_h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(0, 0, 0),
        )

    def _refresh_view(self) -> None:
        if self._raw_frame is None:
            return
        rotated = self._apply_orientation(self._raw_frame)
        self._current_frame = rotated
        self.view.set_frame_bgr(rotated)

    def _on_rotation_changed(self, value: float) -> None:
        prev = self._rotation
        self._rotation = float(value)
        self.slider_rot.blockSignals(True)
        self.slider_rot.setValue(int(round(value * 10)))
        self.slider_rot.blockSignals(False)
        if prev != self._rotation:
            self.view.clear_roi()
            self._refresh_view()

    def _on_flip_h(self, checked: bool) -> None:
        self._flip_h = checked
        self.view.clear_roi()
        self._refresh_view()

    def _on_flip_v(self, checked: bool) -> None:
        self._flip_v = checked
        self.view.clear_roi()
        self._refresh_view()

    def _nudge_rotation(self, delta: float) -> None:
        v = self.spin_rot.value() + delta
        # wrap to [-180, 180]
        while v > 180:
            v -= 360
        while v < -180:
            v += 360
        self.spin_rot.setValue(v)

    # ------------------------------------------------------------- shutdown
    def closeEvent(self, event) -> None:
        self._timer.stop()
        if self._cap is not None:
            self._cap.release()
        self._ocr.shutdown()
        super().closeEvent(event)
