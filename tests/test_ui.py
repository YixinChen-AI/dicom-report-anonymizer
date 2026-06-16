"""UI 无头冒烟测试：构建窗口、前后对照渲染、涂黑保存。"""
from PIL import Image

from tests._synth import make_dicom_file


def test_main_window_builds(qapp):
    from anonymizer.ui.main_window import MainWindow
    win = MainWindow()
    assert win.windowTitle()


def test_scan_review_build_policy(qapp):
    from anonymizer.core.discover import FieldInfo
    from anonymizer.ui.scan_review_page import ScanReviewPage
    page = ScanReviewPage()
    page.populate([
        FieldInfo("DICOM", "PatientName", "PN", "W••n", 5, "假名"),
        FieldInfo("DICOM", "InstitutionName", "LO", "B••r", 5, "去除"),
        FieldInfo("DICOM", "ImageComments", "LT", "A••d", 5, "未知"),
        FieldInfo("XML", "PatientSex", "text", "F", 5, "保留"),
    ])
    # 默认无额外
    p = page.build_policy()
    assert p.extra_remove_dicom == set() and p.keep == set()
    # 改：未知 ImageComments → 去除；去除 InstitutionName → 保留
    for rec in page._rows:
        if rec["name"] == "ImageComments":
            rec["combo"].setCurrentText("去除")
        if rec["name"] == "InstitutionName":
            rec["combo"].setCurrentText("保留")
    p = page.build_policy()
    assert "ImageComments" in p.extra_remove_dicom
    assert "InstitutionName" in p.keep


def test_review_dicom(qapp, tmp_path):
    from anonymizer.ui.review_view import ReviewWidget
    p = make_dicom_file(tmp_path / "a.dcm", patient_name="Wan^XueZhong", patient_id="P13509")
    w = ReviewWidget()
    w.show_dicom(str(p))
    assert w.table.rowCount() > 0
    # 至少有一行 PatientName，前=真名 后=假名
    found = False
    for r in range(w.table.rowCount()):
        if w.table.item(r, 0).text() == "PatientName":
            assert w.table.item(r, 1).text() == "Wan^XueZhong"
            assert w.table.item(r, 2).text() == "Patient_0001"
            found = True
    assert found


def test_review_xml(qapp, tmp_path):
    from anonymizer.ui.review_view import ReviewWidget
    xml = ('<?xml version="1.0" encoding="gb2312"?><NewDataSet><PATIENT>'
           '<PatientNameC>测试名</PatientNameC></PATIENT>'
           '<Report>患者测试名</Report></NewDataSet>')
    p = tmp_path / "P13509_TestPinyin_0.xml"
    p.write_bytes(xml.encode("gb2312"))
    w = ReviewWidget()
    w.show_xml(str(p))
    assert "测试名" in w.xml_before.toPlainText()
    assert "测试名" not in w.xml_after.toPlainText()


def test_redact_canvas(qapp, tmp_path):
    from PySide6.QtCore import QRect
    from anonymizer.ui.redact_view import ImageCanvas
    src = tmp_path / "img.png"
    Image.new("RGB", (40, 30), (255, 255, 255)).save(src)
    canvas = ImageCanvas()
    assert canvas.load(str(src))
    canvas._rects.append(QRect(2, 2, 10, 8))
    out = tmp_path / "red.png"
    canvas.save(str(out))
    assert out.exists()
    # 黑框区域确实变黑
    im = Image.open(out).convert("RGB")
    assert im.getpixel((5, 5)) == (0, 0, 0)
