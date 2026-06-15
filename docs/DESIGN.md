# DICOM + 报告 匿名化工具 — 设计文档（spec）

- 日期：2026-06-15
- 作者：Yixin Chen（陈亦新） + Claude，Codex 交叉审核
- 状态：已与用户确认，进入实现

## 1. 背景与目标

输入是一份医院导出的 FDG 脑 PET/CT 数据集（参考样本 `90+ FDG 脑.zip`，约 3GB，18,969 个文件），按患者分文件夹组织，每个患者含 DICOM 影像 + 结构化 XML 报告 + PDF/JPG 报告图。这些数据里散布大量受保护健康信息（PHI）。

**目标**：一个运行在 Windows 上、界面简洁友好的桌面工具，把整份数据集**去标识（de-identify）**成可用于研究/分享的副本，并产出一张**明文对照表**和一份**运行报告**。**核心信任点：界面要能并排展示"匿名化前 / 后"**，让医生一眼确认 PHI 确实被去掉、影像内容未被破坏，从而信服。

## 2. 数据现状（已核实）

```
90+ FDG 脑/
├── 90+FDG脑.xls                         # 患者总表（真实姓名/ID，整张是 PHI）
├── <患者中文姓名>/                       # 文件夹名 = 患者姓名（PHI），共 90+ 个
│   ├── <检查号>_<拼音名>_0.xml           # 结构化报告（文件名含 ID+姓名，正文含全套 PHI）
│   ├── images/<...>.pdf                 # 报告 PDF（姓名/ID/日期印在图上）
│   ├── images/*.jpg                     # 报告截图（PHI 烧进像素，共 716 张）
│   └── *.dcm                            # PET/CT 影像（共 17,600 张；标签含 PHI）
└── ...
```

文件类型统计：`.dcm` 17,600 / `.jpg` 716 / `.xml` 99 / `.pdf` 85 / `.xls` 1。

## 3. 用户已确认的决策

| 决策点 | 选择 |
|---|---|
| PDF/JPG 报告 | **默认不输出**；工具提供**手动涂黑**功能（可选保留某张去标识副本） |
| 可逆性 | 保留**明文 CSV 对照表**（用户自行严格保管） |
| 假 ID | **顺序编号** `Patient_0001…`，同一患者在所有文件/所有 DICOM 中一致 |
| 检查日期 | **保留原始日期**（有明文对照表、可逆；PET 研究常需日期） |
| 界面/打包 | **Python + PySide6**，PyInstaller 打成单文件 `.exe`（GitHub Actions 构建） |
| UI 核心 | **前 / 后并排对照**（DICOM 标签、XML 文本，PHI 高亮） |

## 4. 去标识规则（按数据类型）

### 4.1 文件夹与文件名
- 患者文件夹 `<中文姓名>/` → `Patient_000N/`
- XML 文件 `<检查号>_<拼音名>_0.xml` → `Patient_000N_<序号>.xml`
- DICOM 文件名若含姓名/ID → 用 SOPInstanceUID 或序号重命名

### 4.2 DICOM（pydicom，遵循 DICOM PS3.15 基本去标识档）
- **清空/替换直接标识符**：PatientName→`Patient_000N`、PatientID→`Patient_000N`、
  PatientBirthDate、PatientAddress、OtherPatientIDs(Sequence)、PatientTelephoneNumbers、
  PatientMotherBirthName、ReferringPhysicianName、PerformingPhysicianName、OperatorsName、
  InstitutionName、InstitutionAddress、StationName、所有 `PersonName(PN)` VR 的标签、
  以及 curve/overlay/private 标签。
- **UID 一致性重映射**：StudyInstanceUID / SeriesInstanceUID / SOPInstanceUID / FrameOfReferenceUID
  等用「确定性哈希 + 工具内 root」重映射 —— 同一原 UID 永远映到同一新 UID（保留 study/series/帧
  结构与内部引用），但断开与原始档案的回溯链。
- **保留日期**（按用户决定）：StudyDate/SeriesDate/AcquisitionDate 等保留原值。
- **移除私有标签**（`remove_private_tags`）：私有标签常藏 PHI。
- **烧录文字检测（不自动改像素，只标红进报告）**：
  `BurnedInAnnotation == 'YES'`、或 Modality ∈ {SC, OT}、或 SOPClassUID 为 Secondary Capture 的实例
  → 列入"需人工复核"清单，可在涂黑界面处理。**默认不动主影像像素**（PT/CT/MR 主序列一般无烧录）。
- 返回 **(before_tags, after_tags) diff**，供 UI 前后对照与报告。

### 4.3 XML 报告
- **双保险**：
  1. 结构解析（ElementTree）后清空已知 PHI 元素/属性（姓名、ID、出生、住址、电话、医院、医生等字段）。
  2. **已知真值精确替换**：从对照表拿到该患者的真实中文姓名、拼音名、检查号/ID，在 XML **原始文本**里
     做精确字符串替换为假 ID —— 这一步与 schema 无关，是漏字段时的安全网。
- 返回 (before_text, after_text) 供对照。

### 4.4 总表 `.xls`
- **不进输出**。读取它作为「真实姓名↔真实 ID」权威来源建对照表（缺失/不可读时退化为从文件夹名 + XML
  文件名推导）。

### 4.5 PDF / JPG
- **默认丢弃，不进输出**。
- 可选：涂黑界面打开某张 → 拖黑框遮挡 PHI → 另存为去标识副本（PNG）。

## 5. 模块结构（单文件单职责，可独立测试/回滚）

```
anonymizer/
  core/
    scanner.py     # 遍历输入树，按患者分组，识别 dicom/xml/pdf/jpg/xls
    crosswalk.py   # 真实→假ID映射，分配 Patient_000N；明文 CSV 读写
    dicom_deid.py  # 单个 DICOM 去标识（标签 + UID 重映射 + 烧录检测）；返回前后 diff
    xml_deid.py    # 单个 XML 报告去标识；返回前后文本
    redact.py      # 给图像/DICOM 帧打黑框（手动涂黑）
    pipeline.py    # 编排：扫描→建表→逐患者处理→写输出（丢 PDF/JPG）→出报告
    verify.py      # ★安全网：回扫输出，残留任何真实姓名/ID 立即报警
    report.py      # 运行报告（数量、去掉的 PHI、需人工复核的标红项）
  ui/
    main_window.py # 选输入/输出、运行、进度日志
    review_view.py # ★前后对照视图（DICOM 标签 / XML 文本并排，PHI 高亮）
    redact_view.py # 手动涂黑视图
  app.py           # 入口
tests/             # 合成 DICOM/XML 单测（含"埋一个 PHI 看 verify 抓不抓得到"）
```

## 6. 数据流

输入根目录 → `scanner` 分组为患者 → `crosswalk` 分配 `Patient_000N` →
对每个患者：`dicom_deid` / `xml_deid` 写入 `output/去标识输出_可分享/Patient_000N/...`，
丢弃 PDF/JPG（除非用户涂黑保留）→ `crosswalk.csv` + 运行报告写入
`output/_对照表与报告_请勿分享/`（与可分享数据物理分离）→ `verify` 回扫可分享数据确认无残留真实 PHI。

## 7. 错误处理与安全红线

1. **公开 repo 绝不提交真实数据/对照表/PHI**：`.gitignore` 全面拦截，仅放代码 + 合成测试数据。
2. **逐文件 try/except**：单个坏文件不拖垮整轮，失败计入报告。
3. **verify 兜底**：写完输出回扫，发现残留真实姓名/ID 在报告里大声标红。
4. **永不静默丢 PHI**：检测到无法自动处理的烧录像素 → 必须在报告里标红、提示人工复核。

## 8. 测试策略（TDD）

- 用 pydicom 在内存里造合成 DICOM（带假 PHI）→ 断言去标识后直接标识符被清、UID 一致变化、私有标签移除。
- 合成 XML → 断言 PHI 字段清空 + 已知真值被替换。
- crosswalk → 断言同一患者全程同一假 ID、CSV 往返一致。
- verify → 故意在输出埋一个真实姓名，断言能被抓到。

## 9. 交付物

1. 工具源码（公开 repo `dicom-report-anonymizer`）。
2. GitHub Actions 自动构建的 Windows 单文件 `.exe`（Release / artifact）。
3. 本设计文档 + 完整报告 `docs/REPORT.md`（含 Codex 交叉审核意见与修正、使用说明）。

## 10. 非目标（YAGNI）

- 第一版**不做 OCR 自动涂黑**（用户默认不输出 PDF/JPG，手动涂黑已够）。
- 不引入重型第三方去标识库（pydicom 自实现 PS3.15，依赖少、好打包）。
- 不处理网络/PACS，只处理本地文件夹。
