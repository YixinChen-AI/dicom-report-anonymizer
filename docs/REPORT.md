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
anonymizer/core/   scanner / crosswalk / dicom_deid / xml_deid /
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

### 字段保留 / 去除策略（2026-06-15 与用户逐项确认）
| 类别 | 处理 | 例子 |
|---|---|---|
| 患者姓名/ID/身份证/住址/电话/出生 | **去除** | 万学中、P13509、110108…、北京海淀 |
| 检查号/住院号/门诊号/Accession | **去除** | 1902263576795、M001593629 |
| 医生/技师姓名与工号 | **去除** | 报告/申请/转诊医师、操作员、CREATED_BY |
| 病区/床号/科室/住院来源 | **去除** | department、bingqu、chuanghao、laiyuan |
| 保险类型/费用/VIP | **去除** | InsuranceType、FactPrice、VIP |
| 医院名称/地址/机构科室 | **去除** | InstitutionName/Address、InstitutionalDepartmentName |
| **设备/工作站/序列号/机型** | **保留** | StationName、DeviceSerialNumber、Manufacturer、nudi |
| **序列/协议/部位/临床诊断/病史/报告正文** | **保留** | SeriesDescription、BodyPartExamined、linchuangzhenduan |
| **性别/年龄/身高/体重/检查日期** | **保留** | 科研所需 |

> DICOM 与 XML 两边的「设备保留 / 机构去除」策略一致。字段表按本院 .NET DataSet 真实字段名编写，站点异构可在 `xml_deid.BLANK_TAGS` 扩展。

### 实时变更日志（`pipeline` log 回调 → UI）
去标识时**逐文件流式显示**改了哪些字段（DICOM 标签 + XML 字段，前→后值），log 风格，便于现场核对，无需事后逐个打开。

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

TDD 开发，**64 项测试全部通过**。含"故意埋一个 PHI 看 verify 抓不抓得到"的对抗测试、Codex 审核后新增的随机盐/preamble/多值UID/正则兜底测试，以及真实数据驱动新增的脏私有标签宽容解析、设备保留、实时日志等测试。

此外用**独立暴力字节扫描**（不依赖工具内部 verify 逻辑）在真实 2 患者样本上复核：原始数据确含真实 PHI（姓名/ID/身份证/住址/医生名），去标识后患者身份 token **零残留**，设备/临床/日期按策略保留。
CI：`tests.yml` 在 ubuntu 无头跑 pytest；`build-windows.yml` 在 windows 打 exe。

---

## 8. Codex 交叉审核与修正

**方法**：用 `codex exec`（模型 gpt-5.5，read-only 沙箱，xhigh 推理）独立、对抗性地审计去标识完整性，
专找"去标识后仍可能残留 PHI 的漏洞"。Codex 共提 **9 高 / 10 中 / 3 低** 项。
我对每条用自己的判断分诊（不盲从），按"真实风险 × 改动成本 × 是否符合用户决策"采纳或记为已知局限。

### 8.1 已采纳并修复（commit `9277eb1`）

| 严重度 | Codex 指出的问题 | 修复 |
|---|---|---|
| 高 | `UidMapper` 盐硬编码，原 UID + 公开代码可复算新 UID 回关联 | 改为**每次运行随机盐** (`token_hex(16)`) |
| 高 | DICOM 128 字节 preamble 未清，原始导出路径/注释随 `save_as` 写回 | 保存前 `ds.preamble = b"\x00"*128` |
| 高 | `crosswalk.csv` 明文写在输出根，分享输出即泄露全部姓名/ID | **分离目录**：去标识数据→`去标识输出_可分享/`，对照表+报告→`_对照表与报告_请勿分享/` |
| 高 | 运行报告含原始路径/患者文件夹名/leak token | 报告随对照表一并放入私密子目录 |
| 高 | XML 正则只匹配 `<Tag>value</Tag>`，漏带属性/空白的标签 | 正则改 `<{tag}\b[^>]*>`（`\b` 防 PatientName 误伤 PatientNameC） |
| 高 | verify 只查已知 secrets，未被 harvest 的 PHI 永不报警 | verify 加**身份证(18)/手机号(11)启发式正则** + 扫描所有可解码文本文件(fail-closed) |
| 中 | 多值(MultiValue) UID 未处理，可残留原 Referenced UID | 统一处理单值与多值 UI 元素 |
| 中 | XML PHI 字段表过窄(医院/科室/床号/医生) | 扩 `BLANK_TAGS`；`harvest_identifiers` 也收医生/地址进 secrets（正文同值替换 + verify 覆盖） |
| 中 | 烧录检测漏封装文档 | `_detect_burned_in` 补 EncapsulatedDocument(封装 PDF/CDA) 标记 |

复验：**52 项测试全部通过**（新增 8 项针对上述修复的测试），真实样本仍**零残留**，preamble 清零，目录分离正确。

### 8.2 评估后记为已知局限（符合用户决策 / YAGNI / 超出本版范围）

| Codex 指出 | 不在本版处理的理由 |
|---|---|
| 像素烧录应 fail-closed / 接 OCR | 用户明确要保留 DICOM 主数据；PET 主图实测无烧录。本版**标红进报告 + 手动涂黑**，不自动丢弃合法影像 |
| 保留所有 DA/DT/TM 超出"保留检查日期" | 用户明确选择"保留检查日期"；如需更严可加 date-shift（已在 DESIGN 列为可选） |
| `StudyDescription/SeriesDescription/ProtocolName` 未清 | 科研需要保留；自由文本里的已知姓名由 `extra_secrets` + verify 正则兜底 |
| verify 不解析 PixelData/封装文档二进制 | 像素级 OCR 超出本版；封装文档已被烧录检测标红人工复核 |
| 未读 `.xls` 总表 | 总表整张是 PHI，默认丢弃；替换/校验依赖文件夹名+XML+DICOM(已验证足够) |
| 单字姓名/顺序编号 re-id | 本工具定位为"带明文对照表的**假名化**"（用户要可逆回溯），非强匿名 |

### 8.3 Codex 总体评价与我的回应

> Codex：*"当前工具更接近'带明文对照表的假名化/有限数据集'，不满足对外强匿名分享。"*

**回应**：这与本工具的**设计定位一致**——用户明确要求"保留明文 CSV 对照表"(可逆假名化)，用于科研内部回溯，而非完全不可逆的对外公开。在该定位下，已落实 Codex 全部高危中可操作项，并把"对照表/报告"与"可分享数据"物理分离、加上启发式残留校验兜底。若未来需要"对外强匿名"，DESIGN 已预留 date-shift、随机伪 ID、OCR 涂黑等扩展点。

### 8.4 第二轮【全面】审核与修正（v0.2.0）

用户要求对整个程序（不只去标识）再审一遍。Codex 提 **6 高 / 13 中 / 6 低**，逐条分诊后已修：

| 严重度 | 问题 | 修复 |
|---|---|---|
| 高 | UI 只看 leaks，全失败也提示"通过"（诚实性 bug） | 引入 `RunReport.status()` **PASS/WARN/FAIL**；成功=零残留**且**零失败 |
| 高 | 复跑同一输出目录混入旧文件 | 去标识输出非空则**拒绝运行** |
| 高 | 输出在输入目录内→把输出当患者 | 禁止输入/输出相同或**互相嵌套**；**先扫描后建目录** |
| 高 | 每患者只读 1 个 DICOM 采集 secrets | 改为**每个序列目录各读一个头**(stop_before_pixels)，并收 AccessionNumber |
| 高 | 检查号若在报告正文不被替换 | `AccessionNumber/PatientUID` 纳入 harvest secrets |
| 中 | 坏 DICOM 被 verify 当成"安全" | verify 读失败 → 标为**"无法验证"**计入 FAIL |
| 中 | 输出重名 SOPUID 静默覆盖 | `_unique_path` 重名追加 `_1/_2` |
| 中 | 单引号/大写 encoding 声明不识别 | `_decode` 兼容单双引号、大小写 |
| 中 | scanner 漏 `.IMA` | DICOM 扩展加 `.ima` |
| 中 | DICOM 缺保险类 tag | 补 `PatientInsurancePlanCodeSequence` 等 |
| 中 | CI 不在 Windows 跑 / 发版前不测 | tests 加 **windows-latest 矩阵**；build 发版**前先 pytest + 导入冒烟** |
| 低 | redact 保存不查返回值 / UID 边界 / 报告无总体状态 | 全部修正 |

**记为已知局限**（设计取舍或低收益）：XML 用文本正则而非 DOM parser（有意，防破坏 .NET DataSet 格式，已多轮真实数据零残留验证）；单字中文姓名不进全文替换（降阈值会误伤，极罕见）；海量日志/单文件预览在 GUI 线程（已限行，单文件预览快，非阻塞痛点）；像素 OCR（超出本版范围，烧录已标红人工复核）。

**复验**：**64 项测试全过**（新增 stale 输出、嵌套输出、PASS/WARN/FAIL、重名、单引号编码、无法验证、UID 边界等回归测试）；真实 2 患者端到端 **状态=PASS、独立暴力扫描零残留、设备保留、医院去除**。

---

## 9. 使用说明

1. 到仓库 Releases 下载 `DicomReportAnonymizer.exe`（或 Actions 构件）。
2. 运行 → 「① 去标识」选输入文件夹（**子目录为各患者**的那一层）与输出文件夹 → 「扫描预览」确认患者数 → 「开始去标识」。
3. 输出分两个子目录：
   - `去标识输出_可分享/` —— 去标识后的 DICOM + 报告，**可对外分享**。
   - `_对照表与报告_请勿分享/` —— `crosswalk.csv`(回溯钥匙) + 运行报告，**含真实信息，切勿随数据分享**。
4. 「② 前后对照」抽查 DICOM/XML 的前后差异确认 PHI 已去除。
5. 「③ 手动涂黑」处理需保留的报告截图。

开发/源码运行见 [README](../README.md)。

---

## 10. 已知局限与免责

- 去标识无法 100% 保证，尤其**烧录在像素里的文字**（默认丢弃 PDF/JPG，DICOM 截图类需人工涂黑）。
- XML 去标识基于已知 .NET DataSet 字段；遇到异构报告格式需扩展字段表（verify 兜底会提示残留）。
- 第一版不含 OCR 自动涂黑（YAGNI）。
- 请按机构伦理与合规要求人工抽查后再使用/分享。
