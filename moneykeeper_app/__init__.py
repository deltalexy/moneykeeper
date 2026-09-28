"""Moneykeeper desktop application."""

import sys
from pathlib import Path

from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QApplication

from .style import APP_STYLE
from .window import MainWindow

APP_DIR = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parent.parent
)


def run() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Moneykeeper")
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(APP_STYLE)
    window = MainWindow(APP_DIR)
    window.show()
    return app.exec_()
