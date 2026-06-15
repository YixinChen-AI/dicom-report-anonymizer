from anonymizer.core.scanner import scan
from tests._synth import write_synth_dataset


def test_scan_groups_patients(tmp_path):
    root = write_synth_dataset(tmp_path / "ds")
    res = scan(root)
    folders = [p.folder_name for p in res.patients]
    assert folders == ["万学中", "乔金庄"]   # 按 Unicode 码点排序，确定且稳定


def test_scan_classifies_files(tmp_path):
    root = write_synth_dataset(tmp_path / "ds")
    res = scan(root)
    pg = [p for p in res.patients if p.folder_name == "万学中"][0]
    assert len(pg.dicom) == 2          # 大小写 .DCM 也算
    assert len(pg.xml) == 1
    assert len(pg.pdf) == 1
    assert len(pg.image) == 1


def test_scan_finds_master_files(tmp_path):
    root = write_synth_dataset(tmp_path / "ds")
    res = scan(root)
    names = [p.name for p in res.master_files]
    assert "master.xls" in names


def test_scan_single_patient_dataset(tmp_path):
    # 单患者数据集也能正确识别（不做脆弱的自动下钻）
    root = tmp_path / "ds"
    write_synth_dataset(root)
    # 删掉第二个患者，只留一个
    import shutil
    shutil.rmtree(root / "乔金庄")
    res = scan(root)
    assert [p.folder_name for p in res.patients] == ["万学中"]
    pg = res.patients[0]
    assert len(pg.dicom) == 2 and len(pg.xml) == 1
