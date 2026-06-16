"""第 3 步：可信结果呈现 —— 状态 + 覆盖率 + 独立残留扫描 + 打开/涂黑。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QPlainTextEdit,
                               QPushButton, QVBoxLayout, QWidget)

from anonymizer.core.pipeline import PRIVATE_SUBDIR

_BANNER = {
    "PASS": ("✅ PASS", "#1a7f37", "#e7f8ec"),
    "WARN": ("⚠ WARN", "#8a6d00", "#fff7d6"),
    "FAIL": ("🛑 FAIL", "#b00", "#ffe3e3"),
}


class ResultPage(QWidget):
    def __init__(self, on_restart, parent=None):
        super().__init__(parent)
        self._output = None
        layout = QVBoxLayout(self)

        self.banner = QLabel()
        self.banner.setStyleSheet("padding:10px; border-radius:6px; font-size:16px;")
        layout.addWidget(self.banner)

        self.coverage = QLabel()
        self.coverage.setWordWrap(True)
        layout.addWidget(self.coverage)

        layout.addWidget(QLabel("<b>独立残留扫描</b>（匿名化后回扫输出，查所有已知真实 PHI + 身份证/手机号正则）："))
        self.residual = QPlainTextEdit(readOnly=True)
        layout.addWidget(self.residual, 1)

        bar = QHBoxLayout()
        b_out = QPushButton("打开输出目录")
        b_priv = QPushButton("打开私密报告/对照表")
        b_redact = QPushButton("手动涂黑报告截图")
        b_restart = QPushButton("↺ 重新开始")
        b_out.clicked.connect(lambda: _open(self._output))
        b_priv.clicked.connect(lambda: _open(str(Path(self._output).parent / PRIVATE_SUBDIR)))
        b_redact.clicked.connect(self._open_redact)
        b_restart.clicked.connect(on_restart)
        for b in (b_out, b_priv, b_redact):
            bar.addWidget(b)
        bar.addStretch(1)
        bar.addWidget(b_restart)
        layout.addLayout(bar)

    def show_report(self, report, input_root, output_root, policy):
        self._output = output_root
        st = report.status()
        text, fg, bg = _BANNER[st]
        leak_line = ("未发现残留" if not report.leaks
                     else f"{len(report.leaks)} 处疑似残留/无法验证")
        self.banner.setText(f"<span style='color:{fg}'><b>{text}</b></span>　{leak_line}")
        self.banner.setStyleSheet(
            f"padding:10px; border-radius:6px; font-size:16px; background:{bg};")

        n_rm = len(policy.extra_remove_dicom) + len(policy.extra_remove_xml)
        self.coverage.setText(
            f"<b>覆盖率：</b>患者 {report.n_patients}；DICOM 去标识 {report.n_dicom}、失败 "
            f"{report.n_dicom_failed}；XML {report.n_xml}、失败 {report.n_xml_failed}；"
            f"丢弃 PDF {report.n_pdf_dropped}、图片 {report.n_image_dropped}；"
            f"疑似烧录 {len(report.burned_in)}。<br>"
            f"<b>策略：</b>默认规则 + 你额外去除 {n_rm} 个标签、强制保留 {len(policy.keep)} 个。<br>"
            f"可分享数据在输出目录；对照表/报告在「{PRIVATE_SUBDIR}」（含真实信息，勿分享）。")

        if not report.leaks:
            self.residual.setPlainText("✅ 0 处残留 —— 输出未发现任何已知真实 PHI 值，"
                                       "且未命中身份证/手机号模式。")
        else:
            lines = [f"🛑 共 {len(report.leaks)} 处，请人工复核："]
            for lk in report.leaks[:300]:
                lines.append(f"  [{lk.kind}] {Path(lk.file).name}  token={lk.token}  {lk.detail}")
            self.residual.setPlainText("\n".join(lines))

    def _open_redact(self):
        from anonymizer.ui.redact_view import RedactWidget
        dlg = QDialog(self)
        dlg.setWindowTitle("手动涂黑")
        dlg.resize(900, 640)
        lay = QVBoxLayout(dlg)
        lay.addWidget(RedactWidget())
        dlg.show()


def _open(path):
    if not path or not Path(path).exists():
        return
    if sys.platform == "darwin":
        subprocess.run(["open", path])
    elif sys.platform.startswith("win"):
        import os
        os.startfile(path)  # noqa: S606
    else:
        subprocess.run(["xdg-open", path])
