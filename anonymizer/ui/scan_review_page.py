"""第 1 步：扫描数据集 → 审核候选标签 → 用户调整 → 产出 Policy。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QFileDialog, QFormLayout, QHBoxLayout, QHeaderView,
                               QLabel, QLineEdit, QMessageBox, QProgressBar,
                               QPushButton, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from anonymizer.core.policy import Policy
from anonymizer.ui.scan_worker import ScanWorker

_COLORS = {"去除": QColor("#ffd6d6"), "假名": QColor("#ffe6c2"),
           "重映射": QColor("#e6e6ff"), "保留": QColor("#d6f5d6"),
           "未知": QColor("#eeeeee")}


class AddTagDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("新增要去除的标签")
        lay = QFormLayout(self)
        self.source = QComboBox()
        self.source.addItems(["DICOM", "XML"])
        self.name = QLineEdit()
        self.name.setPlaceholderText("DICOM keyword 如 PatientAddress，或 XML 字段名 如 ApplyDoctor")
        lay.addRow("来源", self.source)
        lay.addRow("标签/字段名", self.name)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addRow(bb)

    def value(self):
        return self.source.currentText(), self.name.text().strip()


class ScanReviewPage(QWidget):
    proceed = Signal(str, str, object)   # input_root, output_root, Policy

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._rows = []          # [{source, name, default, combo|None, custom}]
        self._scanned_root = None   # 已扫描并据此审核的输入根；防"扫A审A跑B"
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.in_edit = QLineEdit()
        self.in_edit.textChanged.connect(self._on_input_changed)
        self.out_edit = QLineEdit()
        form.addRow("输入文件夹（子目录为各患者）", self._browse(self.in_edit, self._pick_in))
        form.addRow("输出文件夹（空目录）", self._browse(self.out_edit, self._pick_out))
        self.keep_dates = QCheckBox("保留检查日期（科研常需要）")
        self.keep_dates.setChecked(True)
        form.addRow("", self.keep_dates)
        layout.addLayout(form)

        bar = QHBoxLayout()
        self.btn_scan = QPushButton("① 扫描")
        self.btn_scan.clicked.connect(self._scan)
        bar.addWidget(self.btn_scan)
        self.summary = QLabel("先选输入目录并扫描，审核下面将被去除/保留的标签。"
                              "<b>红=去除 橙=假名 蓝=UID重映射 绿=保留 灰=未知(待你判定)</b>")
        self.summary.setWordWrap(True)
        bar.addWidget(self.summary, 1)
        layout.addLayout(bar)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        layout.addWidget(self.progress)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["状态/动作", "来源", "标签/字段", "类型", "命中", "样例(脱敏)"])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.table, 1)

        ops = QHBoxLayout()
        b_add = QPushButton("＋ 新增要去除的标签")
        b_unknown = QPushButton("把所有「未知」设为去除")
        b_add.clicked.connect(self._add_tag)
        b_unknown.clicked.connect(lambda: self._bulk_unknown("去除"))
        ops.addWidget(b_add)
        ops.addWidget(b_unknown)
        ops.addStretch(1)
        self.btn_next = QPushButton("下一步：执行匿名化 →")
        self.btn_next.setEnabled(False)
        self.btn_next.clicked.connect(self._next)
        ops.addWidget(self.btn_next)
        layout.addLayout(ops)

    # ---- pickers ----
    def _browse(self, edit, slot):
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

    def _on_input_changed(self):
        # 扫描后又改了输入 → 之前的审核作废，强制重扫，禁用下一步
        if self._scanned_root and self.in_edit.text().strip() != self._scanned_root:
            self.btn_next.setEnabled(False)

    # ---- 扫描 ----
    def _scan(self):
        root = self.in_edit.text().strip()
        if not root or not Path(root).is_dir():
            QMessageBox.warning(self, "提示", "请先选择有效的输入文件夹。")
            return
        self.btn_scan.setEnabled(False)
        self.btn_next.setEnabled(False)
        self.progress.show()
        self._scanned_root = root
        self._worker = ScanWorker(root)
        self._worker.done.connect(self._on_scanned)
        self._worker.failed.connect(self._on_scan_failed)
        self._worker.start()

    def _on_scan_failed(self, tb):
        self.progress.hide()
        self.btn_scan.setEnabled(True)
        QMessageBox.critical(self, "扫描出错", tb.splitlines()[-1] if tb else "未知错误")

    def _on_scanned(self, scan_result, fields):
        self.progress.hide()
        self.btn_scan.setEnabled(True)
        self.populate(fields)
        n = len(scan_result.patients)
        from collections import Counter
        c = Counter(f.action for f in fields)
        self.summary.setText(
            f"患者 <b>{n}</b>，候选标签 <b>{len(fields)}</b>："
            f"去除 {c.get('去除',0)} · 假名 {c.get('假名',0)} · 重映射 {c.get('重映射',0)} · "
            f"保留 {c.get('保留',0)} · <span style='background:#eee'>未知 {c.get('未知',0)}（请重点审核）</span>"
            "　红=去除 绿=保留")
        self.btn_next.setEnabled(True)

    def populate(self, fields):
        """填表（可被测试直接调用）。"""
        self.table.setRowCount(0)
        self._rows = []
        for fi in fields:
            self._add_row(fi.source, fi.name, fi.kind, fi.count, fi.sample, fi.action)

    def _add_row(self, source, name, kind, count, sample, action, custom=False):
        r = self.table.rowCount()
        self.table.insertRow(r)
        editable = action in ("去除", "保留", "未知")
        if editable:
            combo = QComboBox()
            combo.addItems(["去除", "保留"])
            # 未知=可能藏 PHI → 默认「去除」(fail-closed)；用户审核样例后可改保留
            combo.setCurrentText("保留" if action == "保留" else "去除")
            combo.currentTextChanged.connect(lambda _t, row=r: self._recolor(row))
            self.table.setCellWidget(r, 0, combo)
        else:
            combo = None
            it = QTableWidgetItem(action)
            it.setBackground(_COLORS.get(action, QColor("white")))
            self.table.setItem(r, 0, it)
        for c, val in enumerate([source, name, kind, str(count), sample], start=1):
            it = QTableWidgetItem(val)
            self.table.setItem(r, c, it)
        self._rows.append({"source": source, "name": name, "default": action,
                           "combo": combo, "custom": custom})
        self._recolor(r)

    def _recolor(self, row):
        rec = self._rows[row]
        action = rec["combo"].currentText() if rec["combo"] else rec["default"]
        color = _COLORS.get(action, QColor("white"))
        for c in range(1, self.table.columnCount()):
            it = self.table.item(row, c)
            if it:
                it.setBackground(color)

    def _bulk_unknown(self, target):
        for rec in self._rows:
            if rec["default"] == "未知" and rec["combo"]:
                rec["combo"].setCurrentText(target)

    def _add_tag(self):
        dlg = AddTagDialog(self)
        if dlg.exec() == QDialog.Accepted:
            source, name = dlg.value()
            if name:
                self._add_row(source, name, "自定义", 0, "", "去除", custom=True)

    # ---- 产出 Policy ----
    def build_policy(self) -> Policy:
        extra_dicom, extra_xml = set(), set()
        keep_dicom, keep_xml = set(), set()
        for rec in self._rows:
            if not rec["combo"]:
                continue
            cur = rec["combo"].currentText()
            default, name, source = rec["default"], rec["name"], rec["source"]
            # 默认规则本来就清空的 = 已发现且 default=="去除" 的非自定义行；
            # 自定义行(用户手填)默认规则不认，必须靠 extra_remove 才会被清空。
            removed_by_default = default == "去除" and not rec["custom"]
            extra_set = extra_dicom if source == "DICOM" else extra_xml
            keep_set = keep_dicom if source == "DICOM" else keep_xml
            if cur == "保留" and removed_by_default:
                keep_set.add(name)      # 覆盖默认清空 → 仅本来源强制保留
            elif cur == "去除" and not removed_by_default:
                extra_set.add(name)     # 默认不清空(保留/未知/自定义) → 额外去除
        return Policy(extra_remove_dicom=extra_dicom, extra_remove_xml=extra_xml,
                      keep_dicom=keep_dicom, keep_xml=keep_xml,
                      keep_dates=self.keep_dates.isChecked())

    def _next(self):
        # 必须先扫描，且当前输入与已扫描的一致（防"扫A审A跑B"）
        if not self._scanned_root:
            QMessageBox.warning(self, "提示", "请先扫描输入文件夹。")
            return
        if self.in_edit.text().strip() != self._scanned_root:
            QMessageBox.warning(self, "输入已变更",
                                "输入文件夹已改动，与已审核的扫描结果不一致。\n请重新扫描后再继续。")
            return
        out = self.out_edit.text().strip()
        if not out:
            QMessageBox.warning(self, "提示", "请选择输出文件夹。")
            return
        # 强 PHI 被改成保留 → 二次确认（去除类被改保留；假名行不可编辑，不会进入此列表）
        kept_strong = [rec["name"] for rec in self._rows
                       if rec["combo"] and rec["default"] == "去除" and not rec["custom"]
                       and rec["combo"].currentText() == "保留"]
        if kept_strong:
            if QMessageBox.warning(
                    self, "确认保留强隐私字段",
                    "你把这些本应去除的字段改成了保留：\n" + "、".join(kept_strong[:20])
                    + "\n确定要保留吗？", QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
                return
        self.proceed.emit(self._scanned_root, out, self.build_policy())
