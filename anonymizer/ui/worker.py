"""后台线程：跑 pipeline，发进度信号，避免界面卡死。"""
from __future__ import annotations

import traceback

from PySide6.QtCore import QThread, Signal

from anonymizer.core.pipeline import run_pipeline


class PipelineWorker(QThread):
    progress = Signal(int, int, str)   # done, total, message
    logline = Signal(str)              # 每个文件的字段变更日志
    done = Signal(object)              # RunReport
    failed = Signal(str)

    def __init__(self, input_root, output_root, keep_dates=True):
        super().__init__()
        self._input = input_root
        self._output = output_root
        self._keep_dates = keep_dates

    def run(self):
        try:
            report = run_pipeline(
                self._input, self._output,
                progress=lambda d, t, m: self.progress.emit(d, t, m),
                log=lambda s: self.logline.emit(s),
                keep_dates=self._keep_dates,
            )
            self.done.emit(report)
        except Exception:
            self.failed.emit(traceback.format_exc())
