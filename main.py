"""Entry point for Meter Capture."""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from meter_capture.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Meter Capture")
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
