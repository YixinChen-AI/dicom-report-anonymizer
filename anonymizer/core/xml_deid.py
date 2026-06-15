"""结构化报告（.NET DataSet XML，常见 gb2312 编码）去标识。

策略（双保险，文本级，避免重序列化破坏 .NET DataSet 格式）：
  1. 按已知 PHI 标签名精确替换/清空标签内容（姓名/ID → 假 ID；生日/住址/电话/身份证/
     检查号/医生 → 清空）。schema 定义块（<xs:element name=...>）不受影响。
  2. 用调用方提供的 secrets（真实姓名/ID token）在全文做精确替换，兜底报告正文里的 PHI。

保留科研字段（性别/年龄/身高/体重/检查日期/报告正文结构）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# 姓名 / 主标识 → 替换成假 ID
REPLACE_WITH_PSEUDO = [
    "PatientName", "PatientNameC", "PatientFN", "PatientFNC",
    "PatientSN", "PatientSNC", "PatientID",
]
# 其它 PHI → 清空。标签匹配大小写不敏感；含本院 .NET DataSet 报告的真实字段名，
# 站点异构时可继续扩。保留：设备/序列/协议(StationName/Modality/SeriesDescription)、
# 临床诊断/病史/报告正文、日期、性别/年龄/身高/体重。
BLANK_TAGS = [
    # 患者标识
    "PatientUID", "PatientBirthday", "OutPatientNo", "InPatientNo", "CaseNO",
    "Patient_tel", "patient_cellphone", "Patient_Address", "patient_idcard",
    "AccessionNumber", "StudyInstanceUID", "StudyID",
    # 医生 / 技师 姓名与工号
    "ReportingPhysician", "ReferringPhysician", "PreReferringPhysician",
    "ReportPhysician", "shenqingYiShi", "Operator", "OperatorCode", "CREATED_BY",
    "ReportDoctor", "ExamDoctor", "AuditDoctor", "VerifyDoctor", "ApplyDoctor",
    "RequestDoctor", "OperatorName", "TechnicianName",
    # 病区 / 床号 / 科室 / 住院信息（患者位置类）
    "HospitalName", "Hospital", "Department", "Ward", "BedNo", "BedNumber",
    "department", "bingqu", "chuanghao", "laiyuan",
    # 保险 / 费用 / VIP
    "InsuranceType", "FactPrice", "VIP",
]
# harvest：作为真实姓名 token 收集
HARVEST_NAME_TAGS = ["PatientName", "PatientNameC", "PatientFN", "PatientFNC",
                     "PatientSN", "PatientSNC"]
# harvest：作为真实 ID token 收集
HARVEST_ID_TAGS = ["PatientID", "OutPatientNo", "InPatientNo", "CaseNO",
                   "StudyInstanceUID", "patient_idcard", "Patient_tel",
                   "patient_cellphone"]
# harvest：被清空的人名/地址也收进 secrets（正文同值替换 + verify 覆盖）。
# 只收「姓名/地址」这类会在正文复现的，不收工号/费用/床号（避免误替换数字/通用词）。
HARVEST_TEXT_TAGS = ["Patient_Address", "ReportingPhysician", "ReferringPhysician",
                     "PreReferringPhysician", "ReportPhysician", "shenqingYiShi",
                     "Operator", "CREATED_BY", "ReportDoctor", "ExamDoctor",
                     "AuditDoctor", "HospitalName"]


@dataclass
class XmlDeidResult:
    before_text: str
    after_text: str
    output_bytes: bytes
    encoding: str
    changes: list = field(default_factory=list)   # [(tag, before, after)]


def _decode(data) -> tuple[str, str]:
    if isinstance(data, str):
        return data, "utf-8"
    m = re.search(rb'encoding="([\w\-]+)"', data[:200])
    enc = m.group(1).decode("ascii") if m else "utf-8"
    for codec in (enc, "gbk", "utf-8", "latin-1"):
        try:
            return data.decode(codec), enc
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("latin-1"), enc


def _tag_pattern(tag: str) -> re.Pattern:
    # \b 防前缀冲突（PatientName 不误匹配 PatientNameC）；[^>]* 容忍属性/空白。
    return re.compile(rf"(<{tag}\b[^>]*>)(.*?)(</{tag}>)", re.IGNORECASE | re.DOTALL)


def _inner_values(text: str, tag: str) -> list[str]:
    return [m.group(2) for m in _tag_pattern(tag).finditer(text)]


def harvest_identifiers(data) -> dict:
    """从 XML 抽取该患者所有真实标识 token（供 crosswalk 收集）。"""
    text, _ = _decode(data)
    names, ids = set(), set()
    for tag in HARVEST_NAME_TAGS:
        for v in _inner_values(text, tag):
            if v.strip():
                names.add(v.strip())
    for tag in HARVEST_ID_TAGS:
        for v in _inner_values(text, tag):
            if v.strip():
                ids.add(v.strip())
    # 医生/地址等自由文本 PHI 也收进 secrets（正文同值替换 + verify 覆盖）
    for tag in HARVEST_TEXT_TAGS:
        for v in _inner_values(text, tag):
            if v.strip():
                names.add(v.strip())
    return {"names": names, "ids": ids}


def deidentify_xml(data, pseudo_id: str, secrets=()) -> XmlDeidResult:
    text, enc = _decode(data)
    before = text
    changes: list = []

    def scrub(tag: str, replacement: str):
        nonlocal text
        pat = _tag_pattern(tag)

        def _sub(m):
            old = m.group(2)
            if old != replacement:
                changes.append((tag, old, replacement))
            return m.group(1) + replacement + m.group(3)

        text = pat.sub(_sub, text)

    for tag in REPLACE_WITH_PSEUDO:
        scrub(tag, pseudo_id)
    for tag in BLANK_TAGS:
        scrub(tag, "")

    # 兜底：全文精确替换已知真实 token（长 token 先替换）
    for tok in sorted({s for s in secrets if s and len(str(s)) >= 2}, key=len, reverse=True):
        if tok in text:
            text = text.replace(tok, pseudo_id)

    # 重新编码（保留声明编码；越界字符转实体引用兜底）
    codec = enc if _codec_ok(enc) else "gbk"
    out = text.encode(codec, errors="xmlcharrefreplace")
    return XmlDeidResult(before_text=before, after_text=text, output_bytes=out,
                         encoding=enc, changes=changes)


def _codec_ok(name: str) -> bool:
    try:
        "x".encode(name)
        return True
    except LookupError:
        return False
