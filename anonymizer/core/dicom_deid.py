"""单个 DICOM 数据集去标识（遵循 DICOM PS3.15 基本档思路）。

设计要点：
  - 直接标识符 PatientName/PatientID → 假 ID。
  - 一批 PHI 标签清空（保留科研相关字段：性别/年龄/体重/日期等）。
  - 所有 PersonName(PN) 标签清空（除 PatientName）。
  - UID 一致性重映射：非标准根（不以 1.2.840.10008 开头）的 UID 才重映射，
    标准类/传输语法 UID 保留；同一原 UID → 同一新 UID（保留 study/series 结构）。
  - 移除私有标签、overlay/curve（常藏烧录注释/PHI）。
  - 可选 extra_secrets：把已知真实姓名/ID token 在任意字符串值里替换为假 ID（兜底）。
  - 检测烧录文字（BurnedInAnnotation/SecondaryCapture/SC|OT）→ 标红，不自动改像素。
  - 返回前后 diff，供 UI 对照与报告。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from secrets import token_hex

from pydicom.multival import MultiValue
from pydicom.uid import generate_uid

# DICOM 标准根：以此开头的 UID 是类/传输语法等标准 UID，必须保留。
DICOM_STD_ROOT = "1.2.840.10008"

# Secondary Capture Image Storage 及其家族前缀（疑似含烧录文字）。
SC_SOP_PREFIX = "1.2.840.10008.5.1.4.1.1.7"
# 封装文档（PDF/CDA）SOPClass：内含原始报告，需人工复核。
ENCAPSULATED_SOP_PREFIX = "1.2.840.10008.5.1.4.1.1.104"

# 需要清空的 PHI 标签（保留 PatientSex/Age/Weight/Size/各种 Date 等科研字段）。
BLANK_KEYWORDS = {
    "PatientBirthDate", "PatientBirthTime", "PatientBirthName", "PatientMotherBirthName",
    "PatientAddress", "PatientTelephoneNumbers", "PatientTelecomInformation",
    "OtherPatientIDs", "OtherPatientNames", "OtherPatientIDsSequence",
    "IssuerOfPatientID", "MilitaryRank", "BranchOfService", "MedicalRecordLocator",
    "CountryOfResidence", "RegionOfResidence", "PatientReligiousPreference",
    "PatientComments", "EthnicGroup", "Occupation", "AdditionalPatientHistory",
    "InstitutionName", "InstitutionAddress", "InstitutionalDepartmentName",
    "InstitutionCodeSequence",
    "ReferringPhysicianName", "ReferringPhysicianAddress",
    "ReferringPhysicianTelephoneNumbers", "PhysiciansOfRecord",
    "PerformingPhysicianName", "NameOfPhysiciansReadingStudy", "OperatorsName",
    "RequestingPhysician", "RequestingService", "ScheduledPerformingPhysicianName",
    "StationName", "DeviceSerialNumber",
    "StudyID", "AccessionNumber",
    "AdmissionID", "IssuerOfAdmissionID", "ServiceEpisodeID",
    "PerformedProcedureStepID", "RequestedProcedureID", "ScheduledProcedureStepID",
    "CurrentPatientLocation", "PatientTransportArrangements",
    "OrderCallbackPhoneNumber", "OrderEnteredBy", "OrderEntererLocation",
    "NamesOfIntendedRecipientsOfResults", "HumanPerformersName",
    "HumanPerformersOrganization", "VerifyingObserverName", "ContentCreatorName",
}

# diff 中展示的标签（人最关心的 PHI），其余变更只计数。
_PATIENT_NAME_TAG = (0x0010, 0x0010)
_PATIENT_ID_TAG = (0x0010, 0x0020)


class UidMapper:
    """原 UID → 新 UID 的一致性映射（确定性，便于测试与跨文件一致）。"""

    def __init__(self, salt: str | None = None):
        # 默认每次运行随机盐：新 UID 不可由原 UID + 公开代码复算关联回原检查。
        self._salt = salt if salt is not None else token_hex(16)
        self._map: dict[str, str] = {}

    def __call__(self, original: str) -> str:
        if original not in self._map:
            self._map[original] = generate_uid(entropy_srcs=[self._salt, original])
        return self._map[original]


@dataclass
class DeidResult:
    dataset: object
    changes: list = field(default_factory=list)   # [(label, before, after)]
    uids_remapped: int = 0
    private_removed: int = 0
    burned_in_suspected: bool = False
    burned_in_reason: str = ""


def _iter_datasets(ds):
    """递归 yield ds 本身及所有嵌套序列里的子数据集。"""
    yield ds
    for elem in ds:
        if elem.VR == "SQ" and elem.value is not None:
            for item in elem.value:
                yield from _iter_datasets(item)


def _should_remap_uid(value: str) -> bool:
    return bool(value) and not str(value).startswith(DICOM_STD_ROOT)


def _detect_burned_in(ds) -> tuple[bool, str]:
    if str(ds.get("BurnedInAnnotation", "")).upper() == "YES":
        return True, "BurnedInAnnotation=YES"
    modality = str(ds.get("Modality", "")).upper()
    if modality in {"SC", "OT"}:
        return True, f"Modality={modality}（Secondary Capture/Other，疑似截图）"
    sop = str(ds.get("SOPClassUID", ""))
    if sop.startswith(SC_SOP_PREFIX):
        return True, "SOPClass=Secondary Capture Image Storage"
    if sop.startswith(ENCAPSULATED_SOP_PREFIX) or "EncapsulatedDocument" in ds:
        return True, "EncapsulatedDocument（封装PDF/CDA，内含原始报告，需人工复核）"
    return False, ""


def deidentify_dataset(ds, pseudo_id: str, uid_mapper: UidMapper, *,
                       remove_private: bool = True, keep_dates: bool = True,
                       extra_secrets=None) -> DeidResult:
    res = DeidResult(dataset=ds)
    extra_secrets = sorted(extra_secrets or [], key=len, reverse=True)  # 长 token 先替换

    # 烧录检测（先于改值，读原始 Modality/SOPClass）
    res.burned_in_suspected, res.burned_in_reason = _detect_burned_in(ds)

    # 1) UID 一致性重映射（含 file_meta）
    targets = list(_iter_datasets(ds))
    if getattr(ds, "file_meta", None) is not None:
        targets.append(ds.file_meta)
    for sub in targets:
        for elem in sub:
            if elem.VR != "UI":
                continue
            v = elem.value
            if isinstance(v, (MultiValue, list)):
                new = [uid_mapper(x) if (isinstance(x, str) and _should_remap_uid(x)) else x
                       for x in v]
                if list(new) != list(v):
                    res.uids_remapped += sum(1 for a, b in zip(v, new) if a != b)
                    elem.value = new
            elif isinstance(v, str) and _should_remap_uid(v):
                elem.value = uid_mapper(v)
                res.uids_remapped += 1

    # 2) 清空 PHI 标签 + PN 标签（除 PatientName）+ overlay/curve；替换 PatientName/ID
    for sub in _iter_datasets(ds):
        to_delete = []
        for elem in sub:
            tag = elem.tag
            group = tag.group
            # overlay (60xx) / curve (50xx) 整组移除
            if 0x5000 <= group <= 0x50FF or 0x6000 <= group <= 0x60FF:
                to_delete.append(tag)
                continue
            # 私有标签
            if remove_private and tag.is_private:
                to_delete.append(tag)
                res.private_removed += 1
                continue
            keyword = elem.keyword
            # 直接标识符 → 假 ID
            if (tag.group, tag.element) == _PATIENT_NAME_TAG:
                _record(res, "PatientName", elem.value, pseudo_id)
                elem.value = pseudo_id
                continue
            if (tag.group, tag.element) == _PATIENT_ID_TAG:
                _record(res, "PatientID", elem.value, pseudo_id)
                elem.value = pseudo_id
                continue
            # PHI 字段清空
            if keyword in BLANK_KEYWORDS:
                if elem.VR == "SQ":
                    to_delete.append(tag)
                else:
                    _record(res, keyword, elem.value, "")
                    elem.value = ""
                continue
            # 其余 PersonName 一律清空
            if elem.VR == "PN":
                _record(res, keyword or str(tag), elem.value, "")
                elem.value = ""
                continue
            # extra_secrets 兜底：字符串值里若含已知真实 token → 替换为假 ID
            if extra_secrets and elem.VR in ("LO", "SH", "ST", "LT", "UT", "UC", "CS"):
                if isinstance(elem.value, str) and elem.value:
                    new = elem.value
                    for tok in extra_secrets:
                        if tok in new:
                            new = new.replace(tok, pseudo_id)
                    if new != elem.value:
                        _record(res, keyword or str(tag), elem.value, new)
                        elem.value = new
        for tag in to_delete:
            try:
                del sub[tag]
            except KeyError:
                pass

    # 3) 清空 128 字节 preamble（可能含原始导出路径/系统注释）
    ds.preamble = b"\x00" * 128

    # 4) 日期处理
    if not keep_dates:
        for sub in _iter_datasets(ds):
            for elem in sub:
                if elem.VR in ("DA", "DT") and elem.value:
                    _record(res, elem.keyword or str(elem.tag), elem.value, "")
                    elem.value = ""

    return res


def _record(res: DeidResult, label: str, before, after) -> None:
    before_s = "" if before is None else str(before)
    if before_s != str(after):
        res.changes.append((label, before_s, str(after)))
