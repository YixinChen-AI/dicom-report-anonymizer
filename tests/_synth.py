"""测试用合成数据生成（带假 PHI，绝非真实数据）。"""
from pathlib import Path

import numpy as np
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import (generate_uid, ExplicitVRLittleEndian,
                         PYDICOM_IMPLEMENTATION_UID)

CT_SOP_CLASS = "1.2.840.10008.5.1.4.1.1.2"


def make_dicom_file(path: Path, patient_name="Wan^XueZhong", patient_id="P13509",
                    study_uid=None, series_uid=None, modality="CT",
                    sop_class=CT_SOP_CLASS):
    study_uid = study_uid or generate_uid()
    series_uid = series_uid or generate_uid()
    sop_uid = generate_uid()

    ds = Dataset()
    ds.PatientName = patient_name
    ds.PatientID = patient_id
    ds.PatientBirthDate = "19280708"
    ds.PatientSex = "F"
    ds.PatientWeight = "51.5"
    ds.InstitutionName = "Beijing Hospital PETCT Center"
    ds.StationName = "CTAWP71120"
    ds.StudyDate = "20190227"
    ds.Modality = modality
    ds.StudyInstanceUID = study_uid
    ds.SeriesInstanceUID = series_uid
    ds.SOPInstanceUID = sop_uid
    ds.SOPClassUID = sop_class
    block = ds.private_block(0x0041, "MY PRIVATE", create=True)
    block.add_new(0x01, "LO", "secret note")
    # 最小像素，让它是有效影像
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.Rows = 4
    ds.Columns = 4
    ds.BitsAllocated = 16
    ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 0
    ds.PixelData = (np.arange(16, dtype=np.uint16)).tobytes()

    fm = FileMetaDataset()
    fm.MediaStorageSOPClassUID = sop_class
    fm.MediaStorageSOPInstanceUID = sop_uid
    fm.TransferSyntaxUID = ExplicitVRLittleEndian
    fm.ImplementationClassUID = PYDICOM_IMPLEMENTATION_UID
    ds.file_meta = fm
    ds.preamble = b"\x00" * 128

    path.parent.mkdir(parents=True, exist_ok=True)
    ds.save_as(path, enforce_file_format=True)
    return path


SYNTH_XML = """<?xml version="1.0" encoding="gb2312"?>
<NewDataSet>
  <PATIENT>
    <PatientName>WanPinyin</PatientName>
    <PatientNameC>万学中</PatientNameC>
    <PatientID>P13509</PatientID>
    <PatientBirthday>19280708</PatientBirthday>
    <PatientSex>F</PatientSex>
    <patient_idcard>110108192807085422</patient_idcard>
    <StudyDate>20190227</StudyDate>
  </PATIENT>
  <Report>患者万学中，检查所见正常。</Report>
</NewDataSet>"""


def write_synth_dataset(root: Path):
    """造一个 2 患者的迷你数据集：每人 2 个 DICOM(同一 study) + 1 XML + 1 假pdf + 1 假jpg。"""
    root = Path(root)
    patients = {
        "万学中": ("万学中", "WanPinyin", "P13509"),
        "乔金庄": ("乔金庄", "QiaoPinyin", "P22222"),
    }
    for folder, (cn, py, pid) in patients.items():
        pdir = root / folder
        study = generate_uid()
        series = generate_uid()
        for i in range(2):
            make_dicom_file(pdir / "images" / "BRAIN HD" / f"{generate_uid()}.DCM",
                            patient_name=f"{py}", patient_id=pid,
                            study_uid=study, series_uid=series)
        xml = SYNTH_XML.replace("万学中", cn).replace("WanPinyin", py).replace("P13509", pid)
        (pdir / f"{pid}_{py}_0.xml").write_bytes(xml.encode("gb2312"))
        (pdir / "images" / f"{pid}.pdf").write_bytes(b"%PDF-1.4 fake pdf with name " + cn.encode("gb2312"))
        (pdir / "images" / f"{pid}_1.jpg").write_bytes(b"\xff\xd8\xff\xe0 fake jpg")
    (root / "master.xls").write_bytes(b"fake xls patient list")
    return root
