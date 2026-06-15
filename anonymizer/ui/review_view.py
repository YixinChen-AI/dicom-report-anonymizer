"""前后对照视图：DICOM 标签表 / XML 文本，匿名化前后并排，PHI 高亮。

让医生一眼确认：① PHI 确实被去掉（红）② 科研字段被保留（绿）。
"""
from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QHeaderView, QLabel,
                               QPlainTextEdit, QPushButton, QSplitter,
                               QStackedWidget, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from anonymizer.core.preview import dicom_before_after, xml_before_after

_RED = QColor("#ffd6d6")     # 改动/PHI
_GREEN = QColor("#d6f5d6")   # 保留


class ReviewWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        tip = QLabel("载入任意一个原始文件，工具实时演示匿名化前 / 后的差异，"
                     "供医生核对：<span style='background:#ffd6d6'>红=已去除的隐私</span>　"
                     "<span style='background:#d6f5d6'>绿=保留的科研字段</span>")
        tip.setWordWrap(True)
        layout.addWidget(tip)

        bar = QHBoxLayout()
        btn_dcm = QPushButton("载入 DICOM 文件…")
        btn_xml = QPushButton("载入 XML 报告…")
        btn_dcm.clicked.connect(self._load_dicom)
        btn_xml.clicked.connect(self._load_xml)
        bar.addWidget(btn_dcm)
        bar.addWidget(btn_xml)
        bar.addStretch(1)
        layout.addLayout(bar)

        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)

        # —— DICOM 页 ——
        dcm_page = QWidget()
        dcm_l = QVBoxLayout(dcm_page)
        self.dcm_summary = QLabel("（尚未载入）")
        self.dcm_summary.setWordWrap(True)
        dcm_l.addWidget(self.dcm_summary)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["DICOM 标签", "匿名化前", "匿名化后"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        dcm_l.addWidget(self.table, 1)
        self.stack.addWidget(dcm_page)

        # —— XML 页 ——
        xml_page = QWidget()
        xml_l = QVBoxLayout(xml_page)
        splitter = QSplitter(Qt.Horizontal)
        self.xml_before = QPlainTextEdit(readOnly=True)
        self.xml_after = QPlainTextEdit(readOnly=True)
        for ed, title in ((self.xml_before, "匿名化前"), (self.xml_after, "匿名化后")):
            box = QWidget()
            b = QVBoxLayout(box)
            b.setContentsMargins(0, 0, 0, 0)
            b.addWidget(QLabel(f"<b>{title}</b>"))
            b.addWidget(ed)
            splitter.addWidget(box)
        xml_l.addWidget(splitter, 1)
        self.stack.addWidget(xml_page)

    # ---- DICOM ----
    def _load_dicom(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择一个原始 DICOM 文件", "", "DICOM (*.dcm *.DCM);;所有文件 (*)")
        if path:
            self.show_dicom(path)

    def show_dicom(self, path):
        try:
            rows, summary = dicom_before_after(path)
        except Exception as e:  # noqa: BLE001
            self.dcm_summary.setText(f"<span style='color:red'>读取失败：{e}</span>")
            self.stack.setCurrentIndex(0)
            return

        self.table.setRowCount(0)
        for kw, before, after, changed in rows:
            r = self.table.rowCount()
            self.table.insertRow(r)
            items = [QTableWidgetItem(kw), QTableWidgetItem(before), QTableWidgetItem(after)]
            color = _RED if changed else _GREEN
            for it in items:
                it.setBackground(color)
            for c, it in enumerate(items):
                self.table.setItem(r, c, it)

        burn = ("　<span style='color:#b00'>⚠ 疑似烧录文字：%s（请到「手动涂黑」复核）</span>"
                % summary["burned_in_reason"]) if summary["burned_in"] else ""
        self.dcm_summary.setText(
            f"私有标签移除：<b>{summary['private_removed']}</b> 个　|　"
            f"UID 重映射：<b>{summary['uids_remapped']}</b> 个{burn}")
        self.stack.setCurrentIndex(0)

    # ---- XML ----
    def _load_xml(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择一个原始 XML 报告", "", "XML (*.xml);;所有文件 (*)")
        if path:
            self.show_xml(path)

    def show_xml(self, path):
        try:
            before, after, secrets = xml_before_after(path)
        except Exception as e:  # noqa: BLE001
            self.xml_before.setPlainText(f"读取失败：{e}")
            self.stack.setCurrentIndex(1)
            return
        self.xml_before.setPlainText(before)
        self.xml_after.setPlainText(after)
        _highlight(self.xml_before, secrets, _RED)
        _highlight(self.xml_after, set(re.findall(r"Patient_\d+", after)), _GREEN)
        self.stack.setCurrentIndex(1)


def _highlight(editor: QPlainTextEdit, tokens, color: QColor):
    fmt = QTextCharFormat()
    fmt.setBackground(color)
    doc = editor.document()
    for tok in tokens:
        if not tok:
            continue
        cursor = QTextCursor(doc)
        while True:
            cursor = doc.find(tok, cursor)
            if cursor.isNull():
                break
            cursor.mergeCharFormat(fmt)
