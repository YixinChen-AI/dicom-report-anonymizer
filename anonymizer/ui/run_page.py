"""第 2 步：按确认的策略执行匿名化，实时逐文件变更日志。"""
from __future__ import annotations

from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPlainTextEdit, QProgressBar,
                               QPushButton, QVBoxLayout, QWidget)

from anonymizer.ui.worker import PipelineWorker


class RunPage(QWidget):
    def __init__(self, on_back, on_finished, parent=None):
        super().__init__(parent)
        self._on_finished = on_finished
        self._worker = None
        self._input = self._output = self._policy = None
        self.report = None

        layout = QVBoxLayout(self)
        self.summary = QLabel("策略已确认，点「开始匿名化」。")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

        bar = QHBoxLayout()
        self.btn_back = QPushButton("← 返回修改策略")
        self.btn_start = QPushButton("开始匿名化")
        self.btn_back.clicked.connect(on_back)
        self.btn_start.clicked.connect(self._start)
        bar.addWidget(self.btn_back)
        bar.addWidget(self.btn_start)
        bar.addStretch(1)
        self.btn_result = QPushButton("查看结果 →")
        self.btn_result.setEnabled(False)
        self.btn_result.clicked.connect(lambda: self._on_finished(self.report))
        bar.addWidget(self.btn_result)
        layout.addLayout(bar)

        self.progress = QProgressBar()
        layout.addWidget(self.progress)
        self.log = QPlainTextEdit(readOnly=True)
        self.log.setMaximumBlockCount(100000)
        layout.addWidget(self.log, 1)

    def setup(self, input_root, output_root, policy):
        self._input, self._output, self._policy = input_root, output_root, policy
        n_rm = len(policy.extra_remove_dicom) + len(policy.extra_remove_xml)
        n_keep = len(policy.all_keep())
        self.summary.setText(
            f"输入：{input_root}<br>输出：{output_root}<br>"
            f"策略：默认规则 + 你额外去除 <b>{n_rm}</b> 个标签、强制保留 <b>{n_keep}</b> 个；"
            f"检查日期：{'保留' if policy.keep_dates else '清空'}")
        self.log.clear()
        self.progress.setValue(0)
        self.btn_result.setEnabled(False)
        self.report = None

    def _start(self):
        self.btn_start.setEnabled(False)
        self.btn_back.setEnabled(False)
        self._log("开始处理……")
        self._worker = PipelineWorker(self._input, self._output,
                                      keep_dates=self._policy.keep_dates, policy=self._policy)
        self._worker.progress.connect(self._on_progress)
        self._worker.logline.connect(self._log)
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_progress(self, done, total, _msg):
        if total:
            self.progress.setMaximum(total)
            self.progress.setValue(done)

    def _on_done(self, report):
        self.report = report
        self.btn_start.setEnabled(True)
        self.btn_back.setEnabled(True)
        self.btn_result.setEnabled(True)
        self._log(f"—— 完成（{report.status()}）—— 患者 {report.n_patients}，"
                  f"DICOM {report.n_dicom}，XML {report.n_xml}，失败 "
                  f"{report.n_dicom_failed}/{report.n_xml_failed}，残留 {len(report.leaks)}")
        self._log("点右上「查看结果 →」看可信结果与证据。")

    def _on_failed(self, tb):
        self.btn_start.setEnabled(True)
        self.btn_back.setEnabled(True)
        self._log("处理出错：\n" + tb)

    def _log(self, text):
        self.log.appendPlainText(text)
