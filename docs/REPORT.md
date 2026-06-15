# 医学影像与报告匿名化工具 — 完整报告

- 日期：2026-06-15
- 仓库：https://github.com/YixinChen-AI/dicom-report-anonymizer
- 作者：Yixin Chen（陈亦新）+ Claude（实现）+ Codex（独立交叉审核）
- 参考数据集：`90+ FDG 脑.zip`（医院导出 FDG 脑 PET/CT，约 3GB，18,969 文件）

---

## 1. 概述

本工具把医院导出的 DICOM 影像 + 结构化报告一键**去标识（de-identify）**，用于科研与数据分享。
运行在 Windows 上（PySide6 桌面程序，GitHub Actions 自动构建单文件 `.exe`），核心特点：

- **DICOM 去标识**：按 DICOM PS3.15 基本档清除直接标识符，UID 一致性重映射，移除私有/overlay 标签，保留科研字段（性别/年龄/体重/检查日期）。
- **报告（XML）去标识**：文本级双保险——已知 PHI 字段精确清空/替换 + 已知真实姓名/ID 全文兜底替换。
- **统一假 ID**：同一患者全程映射到同一 `Patient_000N`。
- **明文对照表**：导出 `crosswalk.csv` 供回溯（用户自行严格保管）。
- **前后对照界面**：并排展示匿名化前/后，PHI 红、保留字段绿，让医生信服。
- **手动涂黑**：对含烧录文字的截图手动遮挡 PHI 后另存。
- **隐私校验兜底**：处理完回扫输出，残留真实姓名/ID 立即报警。

---

## 2. 数据现状分析（实测）

zip 内部结构（共 18,969 文件：`.dcm` 17,600 / `.jpg` 716 / `.xml` 99 / `.pdf` 85 / `.xls` 1）：

```
90+ FDG 脑/
├── 90+FDG脑.xls                          # 患者总表（整张是 PHI）
├── <患者中文姓名>/                        # 文件夹名 = 患者姓名（PHI），90+ 个
│   ├── <检查号>_<拼音名>_0.xml            # .NET DataSet 报告（gb2312），文件名+正文含 PHI
│   ├── images/<检查号>.pdf               # 报告 PDF（姓名/ID/日期印在图上）
│   ├── images/*.jpg                      # 报告截图（PHI 烧进像素）
│   └── images/<序列名>/*.DCM             # PET/CT 影像（大写 .DCM，标签含 PHI）
```

实测同一患者存在**三套不同标识**，必须按文件夹分组关联：
- 文件夹名 / XML：中文名 `万学中`、拼音 `WanXueZhong`、检查号 `1902263576795`、住院号 `M001593629`、身份证 `110108192807085422`
- DICOM 标签内部：`PatientName='WAN XUE ZHONG F 90'`、`PatientID='P13509'`

DICOM 实测 PHI 字段：PatientName、PatientID、PatientBirthDate(`19280708`)、InstitutionName(`Beijing Hospital PETCT Center`)、StationName(`CTAWP71120`)、7 个私有标签；主 PET 图（Modality=PT，SOPClass …1.1.128）**无**烧录文字。

XML(.NET DataSet) PHI 字段：`PatientName/PatientNameC/PatientFN/FNC/SN/SNC`、`PatientID/OutPatientNo/InPatientNo/CaseNO/StudyInstanceUID`、`PatientBirthday`、`Patient_tel/patient_cellphone/Patient_Address/patient_idcard`、`AccessionNumber`、`ReportingPhysician/ReferringPhysician`；正文 `Report` 里也会出现患者姓名。

---

## 3. PHI 面清单

| # | PHI 面 | 处理 |
|---|---|---|
| 1 | 文件夹名=中文姓名 | 重命名 `Patient_000N/` |
| 2 | XML 文件名含 ID+拼音名 | 重命名 `Patient_000N_<i>.xml` |
| 3 | XML 正文结构化 PHI 字段 | 精确清空/替换 |
| 4 | XML 报告正文中的姓名 | secrets 全文兜底替换 |
| 5 | DICOM 标签 PHI | PS3.15 清除/替换 |
| 6 | DICOM 内部 PatientID(另一套) | 收进 secrets + 整体替换 |
| 7 | DICOM UID 可回溯 | 一致性重映射 |
| 8 | DICOM 私有/overlay 标签 | 移除 |
| 9 | PDF/JPG 烧录 PHI | 默认丢弃；可手动涂黑 |
| 10 | 总表 .xls | 不进输出 |

---

## 4. 设计与架构

单文件单职责，核心引擎与界面解耦、可独立测试：

```
anonymizer/core/   scanner / crosswalk / dicom_deid / xml_deid / redact /
                   pipeline / verify / report / preview
anonymizer/ui/     main_window / run_view / review_view / redact_view / worker
```

数据流：扫描分组 → 建对照表(assign+harvest) → 逐患者去标识(DICOM/XML，丢 PDF/JPG) →
写 `crosswalk.csv` → verify 回扫 → 运行报告。详见 [`DESIGN.md`](DESIGN.md)。

---

## 5. 去标识规则详解

### DICOM（`dicom_deid.py`）
- PatientName/PatientID → 假 ID；一批 PHI 标签清空（保留 PatientSex/Age/Weight/Size 与各 Date）。
- 所有 `PN` VR 标签清空（除 PatientName）。
- UID：凡不以标准根 `1.2.840.10008` 开头者一致性重映射（含 file_meta），标准类/传输语法 UID 保留。
- 移除私有标签、overlay(60xx)/curve(50xx)。
- `extra_secrets` 兜底：字符串值里含已知真实 token → 替换为假 ID。
- 烧录检测：BurnedInAnnotation=YES / Modality∈{SC,OT} / SOPClass=Secondary Capture → 标红进报告，不自动改像素。

### XML（`xml_deid.py`）
- 文本级（避免重序列化破坏 .NET DataSet 格式）：已知 PHI 标签精确清空/替换 + secrets 全文兜底替换。
- 保留 gb2312 编码与科研字段；schema 定义块不受影响。

### 假 ID 与对照表（`crosswalk.py`）
- 顺序 `Patient_000N`，幂等；secrets 过滤 <2 字符 token 防误伤；明文 CSV（utf-8-sig）往返。

---

## 6. 真实样本验证结果

用真实患者样本（1 XML + 2 DICOM）跑完整 pipeline：

- 收集到的真实 secrets：`万学中 / WanXueZhong / WAN XUE ZHONG F 90 / 1902263576795 / P13509 / M001593629 / 110108192807085422 …`
- **XML 去标识后：零残留**（62 处改动），保留 `<Report>` 正文与 `<PatientSex>`。
- **DICOM 去标识后：零残留**，8 个 UID 重映射、7 个私有标签移除、烧录判定 False（正确）。
- 输出结构：`Patient_0001/Patient_0001_0.xml` + `Patient_0001/images/<序列>/<新UID>.dcm`，PDF/JPG 已丢弃，`crosswalk.csv` + `run_report.md` 生成。
- verify 回扫：`LEAKS: NONE ✓`

---

## 7. 测试

TDD 开发，**44 项测试全部通过**（crosswalk 8 / dicom_deid 9 / xml_deid 9 / scanner 4 / verify 4 / pipeline 4 / preview 2 / ui 4）。含"故意埋一个 PHI 看 verify 抓不抓得到"的对抗测试。
CI：`tests.yml` 在 ubuntu 无头跑 pytest；`build-windows.yml` 在 windows 打 exe。

---

## 8. Codex 交叉审核与修正

> （本节由 Codex 独立审核结果与对应修正填充。）

---

## 9. 使用说明

1. 到仓库 Releases 下载 `DicomReportAnonymizer.exe`（或 Actions 构件）。
2. 运行 → 「① 去标识」选输入文件夹（**子目录为各患者**的那一层）与输出文件夹 → 「扫描预览」确认患者数 → 「开始去标识」。
3. 「② 前后对照」抽查 DICOM/XML 的前后差异确认 PHI 已去除。
4. 「③ 手动涂黑」处理需保留的报告截图。
5. 妥善保管输出里的 `crosswalk.csv`（唯一回溯钥匙，含 PHI）。

开发/源码运行见 [README](../README.md)。

---

## 10. 已知局限与免责

- 去标识无法 100% 保证，尤其**烧录在像素里的文字**（默认丢弃 PDF/JPG，DICOM 截图类需人工涂黑）。
- XML 去标识基于已知 .NET DataSet 字段；遇到异构报告格式需扩展字段表（verify 兜底会提示残留）。
- 第一版不含 OCR 自动涂黑（YAGNI）。
- 请按机构伦理与合规要求人工抽查后再使用/分享。
