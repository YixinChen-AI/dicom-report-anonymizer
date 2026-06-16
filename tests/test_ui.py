"""UI 无头冒烟测试：构建窗口、前后对照渲染、涂黑保存。"""
from PIL import Image

from tests._synth import make_dicom_file


def test_main_window_builds(qapp):
    from anonymizer.ui.main_window import MainWindow
    win = MainWindow()
    assert win.windowTitle()


def _scan_page_with_fields():
    from anonymizer.core.discover import FieldInfo
    from anonymizer.ui.scan_review_page import ScanReviewPage
    page = ScanReviewPage()
    page.populate([
        FieldInfo("DICOM", "PatientName", "PN", "W••n", 5, "假名"),
        FieldInfo("DICOM", "InstitutionName", "LO", "B••r", 5, "去除"),
        FieldInfo("DICOM", "ImageComments", "LT", "A••d", 5, "未知"),
        FieldInfo("XML", "PatientSex", "text", "F", 5, "保留"),
    ])
    return page


def _row(page, name):
    return next(r for r in page._rows if r["name"] == name)


def test_scan_review_build_policy(qapp):
    page = _scan_page_with_fields()
    # 未知 fail-closed：ImageComments 默认就被设为去除（#2）
    assert _row(page, "ImageComments")["combo"].currentText() == "去除"
    p = page.build_policy()
    assert p.extra_remove_dicom == {"ImageComments"}
    assert p.all_keep() == set()
    # 改：去除 InstitutionName → 保留
    _row(page, "InstitutionName")["combo"].setCurrentText("保留")
    p = page.build_policy()
    assert "ImageComments" in p.extra_remove_dicom
    assert "InstitutionName" in p.keep_dicom    # 按来源保留（#4）


def test_unknown_defaults_to_remove_and_can_keep(qapp):
    """#2：未知字段默认去除（fail-closed），改保留后既不去除也不进 keep。"""
    page = _scan_page_with_fields()
    _row(page, "ImageComments")["combo"].setCurrentText("保留")
    p = page.build_policy()
    assert "ImageComments" not in p.extra_remove_dicom
    assert "ImageComments" not in p.all_keep()


def test_custom_remove_tag_enters_policy(qapp):
    """#1：手动新增的待去除标签必须真正进入 Policy.extra_remove_*。"""
    from anonymizer.ui.scan_review_page import ScanReviewPage
    page = ScanReviewPage()
    page.populate([])
    page._add_row("DICOM", "PatientAddress", "自定义", 0, "", "去除", custom=True)
    page._add_row("XML", "ApplyDoctor", "自定义", 0, "", "去除", custom=True)
    p = page.build_policy()
    assert "PatientAddress" in p.extra_remove_dicom
    assert "ApplyDoctor" in p.extra_remove_xml


def test_keep_is_source_scoped(qapp):
    """#4：保留 DICOM 某字段不得连带保留同名 XML 字段。"""
    from anonymizer.core.discover import FieldInfo
    from anonymizer.ui.scan_review_page import ScanReviewPage
    page = ScanReviewPage()
    page.populate([
        FieldInfo("DICOM", "AccessionNumber", "SH", "A••1", 5, "去除"),
        FieldInfo("XML", "AccessionNumber", "text", "A••1", 5, "去除"),
    ])
    # 只把 DICOM 的 AccessionNumber 改成保留
    for rec in page._rows:
        if rec["source"] == "DICOM":
            rec["combo"].setCurrentText("保留")
    p = page.build_policy()
    assert p.forces_keep_dicom("AccessionNumber")
    assert not p.forces_keep_xml("AccessionNumber")   # XML 不受影响


def test_input_change_blocks_next(qapp):
    """#5：扫描后改动输入框 → 禁用下一步，避免用旧策略跑新目录。"""
    page = _scan_page_with_fields()
    page._scanned_root = "/data/A"
    page.in_edit.setText("/data/A")
    page.btn_next.setEnabled(True)
    page.in_edit.setText("/data/B")          # 触发 textChanged
    assert not page.btn_next.isEnabled()


def test_next_emits_scanned_root_not_edit(qapp, tmp_path):
    """#5：proceed 发出的是已扫描的根，而非当前可被篡改的输入框。"""
    page = _scan_page_with_fields()
    page._scanned_root = str(tmp_path / "scanned")
    page.in_edit.blockSignals(True)          # 模拟"扫描后输入框未变"
    page.in_edit.setText(str(tmp_path / "scanned"))
    page.in_edit.blockSignals(False)
    page.out_edit.setText(str(tmp_path / "out"))
    captured = {}
    page.proceed.connect(lambda i, o, _p: captured.update(inp=i, out=o))
    page._next()
    assert captured["inp"] == str(tmp_path / "scanned")


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
