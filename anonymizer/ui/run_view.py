"""去标识主流程页：选输入/输出 → 扫描预览 → 运行 → 进度 → 结果。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QFileDialog, QFormLayout, QHBoxLayout,
                               QLabel, QLineEdit, QMessageBox, QPlainTextEdit,
                               QProgressBar, QPushButton, QVBoxLayout, QWidget)

from anonymizer.core import scanner
from anonymizer.core.pipeline import DATA_SUBDIR, PRIVATE_SUBDIR
from anonymizer.ui.worker import PipelineWorker


class RunWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.in_edit = QLineEdit()
        self.out_edit = QLineEdit()
        form.addRow("输入文件夹（数据集，子目录为各患者）", self._with_browse(self.in_edit, self._pick_in))
        form.addRow("输出文件夹（去标识结果）", self._with_browse(self.out_edit, self._pick_out))
        self.keep_dates = QCheckBox("保留检查日期（推荐：科研常需要；已留明文对照表）")
        self.keep_dates.setChecked(True)
        form.addRow("", self.keep_dates)
        layout.addLayout(form)

        bar = QHBoxLayout()
        self.btn_scan = QPushButton("扫描预览")
        self.btn_run = QPushButton("开始去标识")
        self.btn_scan.clicked.connect(self._scan_preview)
        self.btn_run.clicked.connect(self._run)
        bar.addWidget(self.btn_scan)
        bar.addWidget(self.btn_run)
        bar.addStretch(1)
        layout.addLayout(bar)

        self.preview = QLabel("提示：先「扫描预览」确认检测到的患者数是否正确，再开始。")
        self.preview.setWordWrap(True)
        layout.addWidget(self.preview)

        self.progress = QProgressBar()
        layout.addWidget(self.progress)

        self.log = QPlainTextEdit(readOnly=True)
        self.log.setMaximumBlockCount(100000)   # 限制内存：超大数据集时旧行滚出
        layout.addWidget(self.log, 1)

        res = QHBoxLayout()
        self.btn_open_out = QPushButton("打开输出目录")
        self.btn_report = QPushButton("查看运行报告")
        self.btn_open_out.setEnabled(False)
        self.btn_report.setEnabled(False)
        self.btn_open_out.clicked.connect(lambda: _open_path(self.out_edit.text()))
        self.btn_report.clicked.connect(
            lambda: _open_path(str(Path(self.out_edit.text()) / PRIVATE_SUBDIR / "run_report.md")))
        res.addWidget(self.btn_open_out)
        res.addWidget(self.btn_report)
        res.addStretch(1)
        layout.addLayout(res)

    def _with_browse(self, edit, slot):
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(edit, 1)
        b = QPushButton("浏览…")
        b.clicked.connect(slot)
        h.addWidget(b)
        return w

    def _pick_in(self):
        d = QFileDialog.getExistingDirectory(self, "选择输入文件夹")
        if d:
            self.in_edit.setText(d)

    def _pick_out(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出文件夹")
        if d:
            self.out_edit.setText(d)

    def _scan_preview(self):
        root = self.in_edit.text().strip()
        if not root or not Path(root).is_dir():
            QMessageBox.warning(self, "提示", "请先选择有效的输入文件夹。")
            return
        try:
            res = scanner.scan(root)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "扫描失败", str(e))
            return
        n = len(res.patients)
        names = "、".join(p.folder_name for p in res.patients[:6])
        more = " …" if n > 6 else ""
        n_dcm = sum(len(p.dicom) for p in res.patients)
        n_xml = sum(len(p.xml) for p in res.patients)
        warn = ""
        if n <= 1:
            warn = "<br><span style='color:#b00'>⚠ 只检测到 ≤1 个患者，可能选错了层级（应选「子目录为各患者」的那一层）。</span>"
        self.preview.setText(
            f"检测到 <b>{n}</b> 个患者：{names}{more}<br>"
            f"DICOM {n_dcm} 个，XML 报告 {n_xml} 个，"
            f"另有 PDF/图片将按设置丢弃。{warn}")

    def _run(self):
        root = self.in_edit.text().strip()
        out = self.out_edit.text().strip()
        if not root or not Path(root).is_dir():
            QMessageBox.warning(self, "提示", "请选择有效的输入文件夹。")
            return
        if not out:
            QMessageBox.warning(self, "提示", "请选择输出文件夹。")
            return
        if Path(out).resolve() == Path(root).resolve():
            QMessageBox.warning(self, "提示", "输出文件夹不能和输入相同。")
            return
        self.btn_run.setEnabled(False)
        self.btn_scan.setEnabled(False)
        self.log.clear()
        self.progress.setValue(0)
        self._log("开始处理……")

        self._worker = PipelineWorker(root, out, keep_dates=self.keep_dates.isChecked())
        self._worker.progress.connect(self._on_progress)
        self._worker.logline.connect(self._log)        # 实时字段变更日志
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_progress(self, done, total, msg):
        if total:
            self.progress.setMaximum(total)
            self.progress.setValue(done)

    def _on_done(self, report):
        self.btn_run.setEnabled(True)
        self.btn_scan.setEnabled(True)
        self.btn_open_out.setEnabled(True)
        self.btn_report.setEnabled(True)
        st = report.status()
        self._log("—— 完成 ——")
        self._log(f"患者 {report.n_patients}，DICOM {report.n_dicom}，XML {report.n_xml}，"
                  f"丢弃 PDF {report.n_pdf_dropped}、图片 {report.n_image_dropped}")
        self._log(f"可分享的去标识数据在「{DATA_SUBDIR}」；对照表/报告在「{PRIVATE_SUBDIR}」"
                  f"（含真实信息，切勿随数据一起分享）。")
        if report.n_dicom_failed or report.n_xml_failed:
            self._log(f"⚠ 处理失败：DICOM {report.n_dicom_failed}、XML {report.n_xml_failed}（见报告）。")
        if report.burned_in:
            self._log(f"⚠ {len(report.burned_in)} 个文件疑似烧录文字，请到「手动涂黑」复核。")
        if st == "PASS":
            self._log("✅ PASS：无残留、无失败。")
            QMessageBox.information(self, "完成", "去标识完成 ✅ PASS（无残留、无失败）")
        elif st == "WARN":
            self._log("⚠ WARN：有文件失败或疑似烧录，未发现残留 PHI，请看报告。")
            QMessageBox.warning(self, "完成（需注意）",
                                "完成，但有文件处理失败或疑似烧录，请查看运行报告。")
        else:  # FAIL
            self._log(f"🛑 FAIL：{len(report.leaks)} 处残留/无法验证，务必人工复核！")
            QMessageBox.critical(self, "需复核",
                                 f"发现 {len(report.leaks)} 处残留 PHI 或无法验证的文件，请查看运行报告。")

    def _on_failed(self, tb):
        self.btn_run.setEnabled(True)
        self.btn_scan.setEnabled(True)
        self._log("处理出错：\n" + tb)
        QMessageBox.critical(self, "出错", "处理过程中发生错误，详见日志。")

    def _log(self, text):
        self.log.appendPlainText(text)


def _open_path(path):
    if not path or not Path(path).exists():
        return
    if sys.platform == "darwin":
        subprocess.run(["open", path])
    elif sys.platform.startswith("win"):
        import os
        os.startfile(path)  # noqa: S606
    else:
        subprocess.run(["xdg-open", path])
