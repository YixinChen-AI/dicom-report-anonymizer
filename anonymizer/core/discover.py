"""扫描发现：遍历数据集里实际出现的每个 DICOM 标签 / XML 字段，
聚合出候选清单（样例脱敏 + 命中数 + 建议动作），供用户在第 1 步审核。

只读元数据（DICOM stop_before_pixels），每个序列目录抽 1 个文件即可发现标签。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import pydicom

from .dicom_deid import BLANK_KEYWORDS
from .policy import Policy
from .xml_deid import BLANK_TAGS, REPLACE_WITH_PSEUDO

_BINARY_VR = {"OB", "OW", "OF", "OD", "UN", "SQ"}
_TEXT_VR = {"LO", "SH", "ST", "LT", "UT", "UC", "PN"}

# 已知应保留的 DICOM 设备/科研字段（避免被当成"未知"）
DICOM_KEEP_HINTS = {
    "StationName", "DeviceSerialNumber", "Manufacturer", "ManufacturerModelName",
    "SoftwareVersions", "ProtocolName", "SeriesDescription", "StudyDescription",
    "BodyPartExamined", "PatientSex", "PatientAge", "PatientWeight", "PatientSize",
    "Modality",
}
# 已知应保留的 XML 科研/设备字段
XML_KEEP_HINTS = {
    "PatientSex", "PatientAge", "Patient_Stature", "PATIENT_WEIGHT", "StudyDate",
    "SeriesDate", "SeriesTime", "StudyTime", "WriteDateTime", "ReferringDate",
    "Modality", "SeriesDescription", "StudyDescription", "BodyPartExamined",
    "StationName", "nudi", "linchuangzhenduan", "Lishibingshi", "Report",
    "StudyClass0", "StudyClass1", "StudyClass2", "SeriesNumber", "StudyNo",
    "ImageNumber", "Image_x0020_Count", "studytimes", "INFOTYPE", "ReportStatus",
    "Pathology", "fusion", "StudyComponentType", "WorkFlow",
}


@dataclass
class FieldInfo:
    source: str    # "DICOM" | "XML"
    name: str      # keyword / 标签名
    kind: str      # DICOM VR / "text"
    sample: str    # 脱敏样例
    count: int     # 命中数（DICOM=序列数，XML=报告数）
    action: str    # 去除 | 假名 | 重映射 | 保留 | 未知


def _mask(v: str) -> str:
    v = str(v)
    if len(v) <= 2:
        return "•" * len(v)
    return v[0] + "•" * min(len(v) - 2, 8) + v[-1]


def _dicom_action(keyword: str, vr: str, policy: Policy) -> str:
    if keyword in ("PatientName", "PatientID"):
        return "假名"
    if ((keyword in BLANK_KEYWORDS or policy.adds_remove_dicom(keyword))
            and not policy.forces_keep(keyword)):
        return "去除"
    if vr == "PN" and not policy.forces_keep(keyword):
        return "去除"
    if vr == "UI":
        return "重映射"
    if keyword in DICOM_KEEP_HINTS:
        return "保留"
    if vr in _TEXT_VR:
        return "未知"      # 自由文本，可能藏 PHI，待用户判定
    return "保留"


def _xml_action(tag: str, policy: Policy) -> str:
    if tag in REPLACE_WITH_PSEUDO and not policy.forces_keep(tag):
        return "假名"
    if ((tag in BLANK_TAGS or policy.adds_remove_xml(tag))
            and not policy.forces_keep(tag)):
        return "去除"
    if tag in XML_KEEP_HINTS:
        return "保留"
    return "未知"


_ORDER = {"未知": 0, "去除": 1, "假名": 2, "重映射": 3, "保留": 4}


def discover(scan, policy=None) -> list:
    policy = policy or Policy()
    dmap: dict = {}    # keyword -> [vr, sample, count]
    for pg in scan.patients:
        seen = set()
        for d in pg.dicom:
            if d.parent in seen:
                continue
            seen.add(d.parent)
            try:
                ds = pydicom.dcmread(d, stop_before_pixels=True, force=True)
            except Exception:
                continue
            for e in ds:
                if e.VR in _BINARY_VR:
                    continue
                kw = e.keyword or str(e.tag)
                rec = dmap.setdefault(kw, [e.VR, "", 0])
                rec[2] += 1
                if not rec[1]:
                    try:
                        if str(e.value).strip():
                            rec[1] = _mask(str(e.value))
                    except Exception:
                        pass

    xmap: dict = {}    # tag -> [sample, count]
    for pg in scan.patients:
        for x in pg.xml:
            try:
                txt = x.read_bytes().decode("gbk", "ignore")
            except Exception:
                continue
            for m in re.finditer(r"<([A-Za-z_][\w.\-]*)>([^<]*)</\1>", txt):
                tag, val = m.group(1), m.group(2).strip()
                if tag.startswith("xs"):
                    continue
                rec = xmap.setdefault(tag, ["", 0])
                rec[1] += 1
                if not rec[0] and val:
                    rec[0] = _mask(val)

    out = [FieldInfo("DICOM", kw, vr, s, c, _dicom_action(kw, vr, policy))
           for kw, (vr, s, c) in dmap.items()]
    out += [FieldInfo("XML", tag, "text", s, c, _xml_action(tag, policy))
            for tag, (s, c) in xmap.items()]
    out.sort(key=lambda f: (_ORDER.get(f.action, 9), f.source, f.name))
    return out
