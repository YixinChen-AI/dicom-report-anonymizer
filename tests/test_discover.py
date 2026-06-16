from anonymizer.core.discover import discover
from anonymizer.core.policy import Policy
from anonymizer.core.scanner import scan
from tests._synth import write_synth_dataset


def _fields(tmp_path):
    root = write_synth_dataset(tmp_path / "ds")
    return {(f.source, f.name): f for f in discover(scan(root))}


def test_discover_dicom_actions(tmp_path):
    by = _fields(tmp_path)
    assert by[("DICOM", "PatientName")].action == "假名"
    assert by[("DICOM", "InstitutionName")].action == "去除"
    assert by[("DICOM", "StationName")].action == "保留"     # 设备保留
    assert by[("DICOM", "StudyInstanceUID")].action == "重映射"


def test_discover_xml_actions(tmp_path):
    by = _fields(tmp_path)
    assert by[("XML", "PatientNameC")].action == "假名"
    assert by[("XML", "PatientSex")].action == "保留"
    assert by[("XML", "PatientID")].action == "假名"


def test_discover_sample_is_masked(tmp_path):
    by = _fields(tmp_path)
    # 样例脱敏，不出现完整真实值
    assert "WanPinyin" not in by[("DICOM", "PatientName")].sample
    assert "•" in by[("DICOM", "PatientName")].sample


def test_discover_policy_extra_remove_changes_action(tmp_path):
    root = write_synth_dataset(tmp_path / "ds")
    fields = discover(scan(root), policy=Policy(extra_remove_dicom={"PatientWeight"}))
    by = {(f.source, f.name): f for f in fields}
    assert by[("DICOM", "PatientWeight")].action == "去除"   # 用户额外指定后变去除
