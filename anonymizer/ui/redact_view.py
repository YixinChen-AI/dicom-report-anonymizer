"""手动涂黑视图：打开图片 → 拖拽画黑框遮挡 PHI → 另存为去标识副本。

主要面向报告截图（JPG/PNG 等栅格图）。PDF 请先转成图片再处理。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QLabel, QMessageBox,
                               QPushButton, QScrollArea, QVBoxLayout, QWidget)


class ImageCanvas(QLabel):
    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._image: QImage | None = None
        self._rects: list[QRect] = []
        self._start: QPoint | None = None
        self._cur: QPoint | None = None

    def load(self, path) -> bool:
        img = QImage(str(path))
        if img.isNull():
            return False
        self._image = img.convertToFormat(QImage.Format_RGB32)
        self._rects = []
        self._refresh()
        return True

    def has_image(self) -> bool:
        return self._image is not None

    def undo(self):
        if self._rects:
            self._rects.pop()
            self._refresh()

    def clear_rects(self):
        self._rects = []
        self._refresh()

    def save(self, path):
        if self._image is None:
            return
        out = self._render(preview=False)
        out.save(str(path))

    def _render(self, preview: bool) -> QImage:
        img = self._image.copy()
        p = QPainter(img)
        p.setPen(Qt.NoPen)
        for r in self._rects:
            p.fillRect(r, QColor(0, 0, 0))
        if preview and self._start and self._cur:
            p.fillRect(QRect(self._start, self._cur).normalized(), QColor(0, 0, 0, 120))
        p.end()
        return img

    def _refresh(self):
        if self._image is None:
            return
        pm = QPixmap.fromImage(self._render(preview=True))
        self.setPixmap(pm)
        self.resize(pm.size())

    def mousePressEvent(self, e):
        if self._image is not None:
            self._start = e.position().toPoint()
            self._cur = self._start

    def mouseMoveEvent(self, e):
        if self._start is not None:
            self._cur = e.position().toPoint()
            self._refresh()

    def mouseReleaseEvent(self, e):
        if self._start is not None:
            rect = QRect(self._start, e.position().toPoint()).normalized()
            if rect.width() > 2 and rect.height() > 2:
                self._rects.append(rect)
            self._start = self._cur = None
            self._refresh()


class RedactWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        tip = QLabel("打开报告截图（JPG/PNG），用鼠标拖拽在患者姓名/ID/日期等处画黑框，"
                     "再「保存去标识图片」。PDF 请先转成图片。")
        tip.setWordWrap(True)
        layout.addWidget(tip)

        bar = QHBoxLayout()
        b_open = QPushButton("打开图片…")
        b_undo = QPushButton("撤销")
        b_clear = QPushButton("清空")
        b_save = QPushButton("保存去标识图片…")
        b_open.clicked.connect(self._open)
        b_undo.clicked.connect(lambda: self.canvas.undo())
        b_clear.clicked.connect(lambda: self.canvas.clear_rects())
        b_save.clicked.connect(self._save)
        for b in (b_open, b_undo, b_clear, b_save):
            bar.addWidget(b)
        bar.addStretch(1)
        layout.addLayout(bar)

        self.canvas = ImageCanvas()
        scroll = QScrollArea()
        scroll.setWidget(self.canvas)
        scroll.setWidgetResizable(False)
        layout.addWidget(scroll, 1)

    def _open(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "打开图片", "", "图片 (*.jpg *.jpeg *.png *.bmp *.tif *.tiff);;所有文件 (*)")
        if path and not self.canvas.load(path):
            QMessageBox.warning(self, "打开失败", "无法读取该图片。")

    def _save(self):
        if not self.canvas.has_image():
            QMessageBox.information(self, "提示", "请先打开一张图片。")
            return
        path, _ = QFileDialog.getSaveFileName(self, "保存去标识图片", "redacted.png",
                                              "PNG 图片 (*.png)")
        if path:
            if not path.lower().endswith(".png"):
                path = str(Path(path).with_suffix(".png"))
            self.canvas.save(path)
            QMessageBox.information(self, "已保存", f"已保存到：\n{path}")
