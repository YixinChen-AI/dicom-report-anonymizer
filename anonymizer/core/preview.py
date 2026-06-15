"""为 UI「前后对照」计算单个文件的匿名化前/后内容（无 Qt 依赖，可测试）。"""
from __future__ import annotations

from pathlib import Path

import pydicom

from .dicom_deid import UidMapper, deidentify_dataset
from .xml_deid import deidentify_xml, harvest_identifiers

# 对照表里展示的标签（人最关心的 PHI + 保留的科研字段）。
DISPLAY_TAGS = [
    "PatientName", "PatientID", "PatientBirthDate", "PatientSex", "PatientAge",
    "PatientWeight", "PatientSize", "InstitutionName", "InstitutionAddress",
    "StationName", "ReferringPhysicianName", "PerformingPhysicianName",
    "OperatorsName", "AccessionNumber", "StudyID", "StudyDate", "SeriesDate",
    "Modality", "StudyDescription", "SeriesDescription",
    "StudyInstanceUID", "SeriesInstanceUID", "SOPInstanceUID",
]


def dicom_before_after(path, pseudo: str = "Patient_0001"):
    """返回 (rows, summary)。rows = [(keyword, before, after, changed)]。"""
    ds = pydicom.dcmread(path, force=True)
    before = {kw: str(ds.get(kw, "")) for kw in DISPLAY_TAGS}
    n_priv_before = sum(1 for e in ds if e.tag.is_private)

    res = deidentify_dataset(ds, pseudo, UidMapper())
    after = {kw: str(res.dataset.get(kw, "")) for kw in DISPLAY_TAGS}

    rows = []
    for kw in DISPLAY_TAGS:
        b, a = before[kw], after[kw]
        if b == "" and a == "":
            continue   # 该文件没有这个标签
        rows.append((kw, b, a, b != a))

    summary = {
        "private_before": n_priv_before,
        "private_removed": res.private_removed,
        "uids_remapped": res.uids_remapped,
        "burned_in": res.burned_in_suspected,
        "burned_in_reason": res.burned_in_reason,
    }
    return rows, summary


def secrets_for_xml(path) -> set:
    data = Path(path).read_bytes()
    ident = harvest_identifiers(data)
    secrets = set(ident["names"]) | set(ident["ids"])
    for piece in Path(path).stem.split("_"):
        if piece and len(piece) >= 2:
            secrets.add(piece)
    return {s for s in secrets if s and len(s) >= 2}


def xml_before_after(path, pseudo: str = "Patient_0001"):
    """返回 (before_text, after_text, secrets)。"""
    data = Path(path).read_bytes()
    secrets = secrets_for_xml(path)
    res = deidentify_xml(data, pseudo, secrets=secrets)
    return res.before_text, res.after_text, sorted(secrets, key=len, reverse=True)
