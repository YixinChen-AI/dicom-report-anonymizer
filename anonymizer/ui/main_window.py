"""主窗口：三个标签页 —— 去标识 / 前后对照 / 手动涂黑。"""
from __future__ import annotations

from PySide6.QtWidgets import QLabel, QMainWindow, QTabWidget, QVBoxLayout, QWidget

from anonymizer.ui.redact_view import RedactWidget
from anonymizer.ui.review_view import ReviewWidget
from anonymizer.ui.run_view import RunWidget

APP_TITLE = "DICOM 报告匿名化工具"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(960, 680)

        central = QWidget()
        layout = QVBoxLayout(central)

        disclaimer = QLabel(
            "⚠ 去标识无法 100% 保证（尤其烧录在像素里的文字）。"
            "请人工抽查并按机构合规要求复核。对照表 crosswalk.csv 含真实信息，请严格保管。")
        disclaimer.setWordWrap(True)
        disclaimer.setStyleSheet("color:#8a6d00; background:#fff7d6; padding:6px; border-radius:4px;")
        layout.addWidget(disclaimer)

        tabs = QTabWidget()
        tabs.addTab(RunWidget(), "① 去标识")
        tabs.addTab(ReviewWidget(), "② 前后对照")
        tabs.addTab(RedactWidget(), "③ 手动涂黑")
        layout.addWidget(tabs, 1)

        self.setCentralWidget(central)
