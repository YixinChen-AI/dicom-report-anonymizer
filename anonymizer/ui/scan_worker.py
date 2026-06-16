"""后台线程：扫描数据集 + 发现候选标签。"""
from __future__ import annotations

import traceback

from PySide6.QtCore import QThread, Signal

from anonymizer.core import scanner
from anonymizer.core.discover import discover


class ScanWorker(QThread):
    done = Signal(object, object)   # ScanResult, list[FieldInfo]
    failed = Signal(str)

    def __init__(self, input_root):
        super().__init__()
        self._input = input_root

    def run(self):
        try:
            sc = scanner.scan(self._input)
            fields = discover(sc)
            self.done.emit(sc, fields)
        except Exception:
            self.failed.emit(traceback.format_exc())
