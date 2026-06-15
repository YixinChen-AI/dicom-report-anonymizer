from anonymizer.core.preview import dicom_before_after, xml_before_after
from tests._synth import make_dicom_file


def test_dicom_before_after(tmp_path):
    p = make_dicom_file(tmp_path / "a.dcm", patient_name="Wan^XueZhong", patient_id="P13509")
    rows, summary = dicom_before_after(p, "Patient_0001")
    by_kw = {kw: (b, a, ch) for kw, b, a, ch in rows}
    # PatientName 前后不同，标记 changed
    assert by_kw["PatientName"][0] == "Wan^XueZhong"
    assert by_kw["PatientName"][1] == "Patient_0001"
    assert by_kw["PatientName"][2] is True
    # 体重保留，不算 changed
    assert by_kw["PatientWeight"][2] is False
    # 生日被清空
    assert by_kw["PatientBirthDate"][1] == ""
    assert summary["private_removed"] >= 1


def test_xml_before_after(tmp_path):
    xml = ('<?xml version="1.0" encoding="gb2312"?><NewDataSet><PATIENT>'
           '<PatientNameC>测试名</PatientNameC><PatientID>P13509</PatientID>'
           '<PatientSex>F</PatientSex></PATIENT>'
           '<Report>患者测试名</Report></NewDataSet>')
    p = tmp_path / "P13509_TestPinyin_0.xml"
    p.write_bytes(xml.encode("gb2312"))
    before, after, secrets = xml_before_after(p, "Patient_0001")
    assert "测试名" in before
    assert "测试名" not in after
    assert "<PatientSex>F</PatientSex>" in after   # 科研字段保留
