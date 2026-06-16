"""主窗口：三步向导 —— ① 扫描·审核策略 → ② 执行匿名化 → ③ 可信结果。"""
from __future__ import annotations

from PySide6.QtWidgets import (QLabel, QMainWindow, QMessageBox, QStackedWidget,
                               QVBoxLayout, QWidget)

from anonymizer.ui.result_page import ResultPage
from anonymizer.ui.run_page import RunPage
from anonymizer.ui.scan_review_page import ScanReviewPage

APP_TITLE = "DICOM 报告匿名化工具"
_STEPS = ["① 扫描·审核策略", "② 执行匿名化", "③ 可信结果"]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1000, 720)

        central = QWidget()
        layout = QVBoxLayout(central)

        disclaimer = QLabel(
            "⚠ 去标识无法 100% 保证（尤其烧录在像素里的文字）。请人工抽查并按机构合规复核。"
            "对照表 crosswalk.csv 含真实信息，请严格保管、勿随数据分享。")
        disclaimer.setWordWrap(True)
        disclaimer.setStyleSheet("color:#8a6d00; background:#fff7d6; padding:6px; border-radius:4px;")
        layout.addWidget(disclaimer)

        self.steplabel = QLabel()
        self.steplabel.setStyleSheet("font-size:15px; padding:4px;")
        layout.addWidget(self.steplabel)

        self.stack = QStackedWidget()
        self.scan_page = ScanReviewPage()
        self.run_page = RunPage(on_back=lambda: self._goto(0), on_finished=self._to_result)
        self.result_page = ResultPage(on_restart=lambda: self._goto(0))
        for p in (self.scan_page, self.run_page, self.result_page):
            self.stack.addWidget(p)
        layout.addWidget(self.stack, 1)

        self.scan_page.proceed.connect(self._to_run)
        self.setCentralWidget(central)
        self._goto(0)

    def _goto(self, i):
        self.stack.setCurrentIndex(i)
        self.steplabel.setText("　→　".join(
            f"<b>{s}</b>" if k == i else f"<span style='color:#999'>{s}</span>"
            for k, s in enumerate(_STEPS)))

    def _to_run(self, input_root, output_root, policy):
        self.run_page.setup(input_root, output_root, policy)
        self._goto(1)

    def _to_result(self, report):
        if report is None:
            return
        self.result_page.show_report(report, self.run_page._input,
                                     self.run_page._output, self.run_page._policy)
        self._goto(2)

    def closeEvent(self, e):
        # 后台线程仍在跑时直接销毁会 "QThread: Destroyed while running" 甚至崩溃；
        # 不能 terminate(去标识写一半会留残文件)，只能等当前任务结束。
        running = [w for w in (self.scan_page._worker, self.run_page._worker)
                   if w is not None and w.isRunning()]
        if running:
            if QMessageBox.question(
                    self, "仍在处理",
                    "扫描/匿名化尚未完成。退出将等待当前任务结束，确定退出吗？",
                    QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
                e.ignore()
                return
            for w in running:
                w.wait()
        super().closeEvent(e)
