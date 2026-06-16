"""dicom_deid 模块测试（TDD）。用 pydicom 造合成 DICOM。"""
import pydicom
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import generate_uid, ExplicitVRLittleEndian, PYDICOM_IMPLEMENTATION_UID

from anonymizer.core.dicom_deid import deidentify_dataset, UidMapper

CT_SOP_CLASS = "1.2.840.10008.5.1.4.1.1.2"          # CT Image Storage（标准根，应保留）
SC_SOP_CLASS = "1.2.840.10008.5.1.4.1.1.7"          # Secondary Capture（疑似烧录）


def _make_ds(sop_class=CT_SOP_CLASS, modality="CT", burned="NO"):
    study_uid = generate_uid()
    series_uid = generate_uid()
    sop_uid = generate_uid()

    ds = Dataset()
    ds.PatientName = "Wan^XueZhong"
    ds.PatientID = "1902263576795"
    ds.PatientBirthDate = "19500101"
    ds.PatientSex = "M"
    ds.PatientAge = "070Y"
    ds.PatientWeight = "65"                          # PET SUV 需要，应保留
    ds.PatientAddress = "Beijing Haidian"
    ds.InstitutionName = "Peking University Hospital"
    ds.StationName = "CTAWP71120"
    ds.DeviceSerialNumber = "SN12345"
    ds.ReferringPhysicianName = "Dr^Zhang"
    ds.OperatorsName = "Tech^Li"
    ds.AccessionNumber = "ACC123456"
    ds.StudyDate = "20190228"                        # 保留日期
    ds.Modality = modality
    ds.BurnedInAnnotation = burned
    ds.StudyInstanceUID = study_uid
    ds.SeriesInstanceUID = series_uid
    ds.SOPInstanceUID = sop_uid
    ds.SOPClassUID = sop_class
    ds.FrameOfReferenceUID = generate_uid()
    # 私有标签（常藏 PHI）
    block = ds.private_block(0x0041, "MY PRIVATE", create=True)
    block.add_new(0x01, "LO", "secret patient note")

    fm = FileMetaDataset()
    fm.MediaStorageSOPClassUID = sop_class
    fm.MediaStorageSOPInstanceUID = sop_uid
    fm.TransferSyntaxUID = ExplicitVRLittleEndian
    fm.ImplementationClassUID = PYDICOM_IMPLEMENTATION_UID
    ds.file_meta = fm
    return ds


def test_direct_identifiers_replaced_with_pseudo():
    ds = _make_ds()
    res = deidentify_dataset(ds, "Patient_0001", UidMapper())
    assert str(res.dataset.PatientName) == "Patient_0001"
    assert res.dataset.PatientID == "Patient_0001"


def test_phi_fields_blanked():
    ds = _make_ds()
    res = deidentify_dataset(ds, "Patient_0001", UidMapper())
    d = res.dataset
    assert d.PatientBirthDate == ""
    assert d.PatientAddress == ""
    assert d.InstitutionName == ""
    assert str(d.ReferringPhysicianName) == ""
    assert str(d.OperatorsName) == ""
    assert d.AccessionNumber == ""


def test_research_fields_preserved():
    ds = _make_ds()
    res = deidentify_dataset(ds, "Patient_0001", UidMapper())
    d = res.dataset
    assert d.PatientSex == "M"
    assert d.PatientAge == "070Y"
    assert str(d.PatientWeight) == "65"
    assert d.StudyDate == "20190228"      # 日期保留
    assert d.StationName == "CTAWP71120"  # 设备保留（用户决定）
    assert d.DeviceSerialNumber == "SN12345"


def test_private_tags_removed():
    ds = _make_ds()
    res = deidentify_dataset(ds, "Patient_0001", UidMapper())
    # 私有标签 (0041,xx10) 应被移除
    assert (0x0041, 0x1001) not in res.dataset
    assert res.private_removed >= 1


def test_uids_remapped_but_class_kept():
    ds = _make_ds()
    orig_study = ds.StudyInstanceUID
    orig_sop = ds.SOPInstanceUID
    res = deidentify_dataset(ds, "Patient_0001", UidMapper())
    d = res.dataset
    assert d.StudyInstanceUID != orig_study           # 实例 UID 变了
    assert d.SOPInstanceUID != orig_sop
    assert d.SOPClassUID == CT_SOP_CLASS              # 标准类 UID 不变
    assert d.file_meta.TransferSyntaxUID == ExplicitVRLittleEndian
    # file_meta 的实例 UID 与数据集 SOPInstanceUID 保持一致
    assert d.file_meta.MediaStorageSOPInstanceUID == d.SOPInstanceUID


def test_uid_mapping_consistent_across_files():
    """同一原 UID 在不同文件里映射到同一个新 UID（保留 study/series 结构）。"""
    mapper = UidMapper()
    ds1 = _make_ds()
    ds2 = _make_ds()
    shared_study = generate_uid()
    ds1.StudyInstanceUID = shared_study
    ds2.StudyInstanceUID = shared_study
    r1 = deidentify_dataset(ds1, "Patient_0001", mapper)
    r2 = deidentify_dataset(ds2, "Patient_0001", mapper)
    assert r1.dataset.StudyInstanceUID == r2.dataset.StudyInstanceUID


def test_burned_in_detection():
    normal = deidentify_dataset(_make_ds(), "Patient_0001", UidMapper())
    assert normal.burned_in_suspected is False

    sc = deidentify_dataset(
        _make_ds(sop_class=SC_SOP_CLASS, modality="SC", burned="YES"),
        "Patient_0001", UidMapper())
    assert sc.burned_in_suspected is True
    assert sc.burned_in_reason


def test_changes_diff_recorded():
    ds = _make_ds()
    res = deidentify_dataset(ds, "Patient_0001", UidMapper())
    labels = {c[0] for c in res.changes}
    assert "PatientName" in labels
    # 记录的是 (label, before, after)
    pn = [c for c in res.changes if c[0] == "PatientName"][0]
    assert pn[1] == "Wan^XueZhong"
    assert pn[2] == "Patient_0001"


def test_should_remap_uid_boundary():
    from anonymizer.core.dicom_deid import _should_remap_uid
    assert _should_remap_uid("1.2.840.99999.1") is True      # 厂商 UID → 重映射
    assert _should_remap_uid("1.2.840.10008.5.1.4") is False  # 标准 UID → 保留
    assert _should_remap_uid("1.2.840.100080000.1") is True   # 非标准根(无边界) → 重映射


def test_uid_mapper_random_salt():
    u1, u2 = UidMapper(), UidMapper()
    uid = "1.2.999.55"
    assert u1(uid) != u2(uid)     # 不同运行随机盐 → 新 UID 不可复算关联
    assert u1(uid) == u1(uid)     # 同实例内一致


def test_multivalue_uid_remapped():
    ds = Dataset()
    ds.add_new(0x0008010D, "UI", ["1.2.999.0.1", "1.2.999.0.2"])
    res = deidentify_dataset(ds, "Patient_0001", UidMapper())
    vals = list(res.dataset[0x0008010D].value)
    assert vals != ["1.2.999.0.1", "1.2.999.0.2"]
    assert len(vals) == 2 and vals[0] != vals[1]


def test_preamble_cleared():
    ds = _make_ds()
    ds.preamble = b"\x01" * 128
    res = deidentify_dataset(ds, "Patient_0001", UidMapper())
    assert res.dataset.preamble == b"\x00" * 128


def test_encapsulated_document_flagged():
    res = deidentify_dataset(
        _make_ds(sop_class="1.2.840.10008.5.1.4.1.1.104.1"), "Patient_0001", UidMapper())
    assert res.burned_in_suspected is True


def test_idempotent_no_phi_left():
    """去标识后再扫一遍，原始姓名/ID 不应出现在任何标签值里。"""
    ds = _make_ds()
    res = deidentify_dataset(ds, "Patient_0001", UidMapper())
    leaked = []
    for elem in res.dataset.iterall():
        if elem.VR not in ("OB", "OW", "OF", "UN", "SQ"):
            val = str(elem.value)
            if "Wan^XueZhong" in val or "1902263576795" in val or "Peking" in val:
                leaked.append(elem.tag)
    assert leaked == []
