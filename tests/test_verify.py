from pathlib import Path

from anonymizer.core.verify import verify_text, verify_dicom_file, verify_output_tree
from tests._synth import make_dicom_file


def test_verify_text_finds_token():
    leaks = verify_text("报告：患者万学中正常", ["万学中", "李四"])
    tokens = [t for t, _ in leaks]
    assert "万学中" in tokens
    assert "李四" not in tokens


def test_verify_text_clean():
    assert verify_text("Patient_0001 报告正常", ["万学中"]) == []


def test_verify_text_regex_catches_idcard_phone():
    # 即使未进 secrets，身份证/手机号也被启发式正则抓到
    leaks = verify_text("身份证 110108199001011234，手机 13800138000", [])
    labels = [t for t, _ in leaks]
    assert "身份证号" in labels
    assert "手机号" in labels


def test_verify_regex_no_false_positive_in_filename():
    # 嵌在字母数字文件名/UID 里的数字段不应误报手机号
    leaks = verify_text("<Imagefilename>93c13849794435d7.dcm</Imagefilename>", [])
    assert leaks == []


def test_verify_dicom_finds_planted_leak(tmp_path):
    p = make_dicom_file(tmp_path / "a.dcm", patient_name="Wan^XueZhong", patient_id="P13509")
    leaks = verify_dicom_file(p, ["Wan^XueZhong", "P13509"])
    tokens = {t for _, t in leaks}
    assert "P13509" in tokens


def test_verify_output_tree_ignores_crosswalk(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    # crosswalk.csv 含真实姓名是允许的，不应报 leak
    (out / "crosswalk.csv").write_text("pseudo_id,real\nPatient_0001,万学中", encoding="utf-8")
    # 但普通输出文件里残留真实姓名 = leak
    (out / "Patient_0001.xml").write_text("患者万学中", encoding="utf-8")
    leaks = verify_output_tree(out, ["万学中"])
    files = {Path(l.file).name for l in leaks}
    assert "Patient_0001.xml" in files
    assert "crosswalk.csv" not in files
