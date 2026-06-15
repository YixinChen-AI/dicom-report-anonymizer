"""程序入口：启动匿名化工具界面。"""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from anonymizer.ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
