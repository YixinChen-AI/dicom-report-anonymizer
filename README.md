# DICOM Report Anonymizer · 医学影像与报告匿名化工具

一个运行在 **Windows** 上、界面简洁友好的桌面工具，把医院导出的 **DICOM 影像 + 结构化报告（XML）** 一键**去标识（de-identify）**，用于科研与数据分享。

> ⚠️ **隐私红线**：本仓库**只含工具代码与合成测试数据**，绝不包含任何真实患者数据或对照表。请勿把真实数据、生成的对照表 CSV、或去标识输出提交到任何 git 仓库。

## 能做什么

- **DICOM 去标识**：按 DICOM PS3.15 基本档清除患者姓名、ID、出生日期、住址、电话、医生、机构等直接标识符；UID 一致性重映射（保留 study/series 结构，断开回溯链）；移除私有标签；可选保留检查日期。
- **报告（XML）去标识**：清空 PHI 字段 + 已知真实姓名/ID 全文精确替换（双保险）。
- **统一假 ID**：同一患者在所有文件、所有 DICOM 中映射到同一个 `Patient_0001` 顺序编号。
- **明文对照表**：导出 `crosswalk.csv`（真实 ↔ 假 ID），供你自行严格保管、需要时回溯。
- **★ 前后对照界面**：并排展示匿名化"前 / 后"的 DICOM 标签与报告文本，PHI 高亮，让医生一眼确认、信得过。
- **手动涂黑**：对含烧录文字的图像/截图，手动拖黑框遮挡 PHI 后另存。
- **运行报告**：处理数量、去掉的 PHI、需人工复核的标红项一目了然。

## 快速使用（Windows）

1. 到 [Releases](../../releases) 下载最新的 `DicomReportAnonymizer.exe`（由 GitHub Actions 自动构建）。
2. 双击运行，选择**输入文件夹**（解压好的数据集，**子目录为各患者**的那一层）和**输出文件夹**。
3. 「扫描预览」确认患者数 → 「开始去标识」，完成后在「前后对照」里抽查确认。
4. 输出分两个子目录：`去标识输出_可分享/`（可对外分享）和 `_对照表与报告_请勿分享/`（含 `crosswalk.csv` 回溯钥匙，**切勿随数据分享**）。

## 从源码运行 / 开发

```bash
python3.11 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
pytest                              # 跑测试
python -m anonymizer.app           # 启动界面
```

## 设计与报告

- 设计文档：[`docs/DESIGN.md`](docs/DESIGN.md)
- 完整报告（含 Codex 交叉审核）：[`docs/REPORT.md`](docs/REPORT.md)

## 免责声明

去标识无法 100% 保证（尤其烧录在像素里的文字）。使用前请人工抽查、按你机构的伦理与合规要求复核。本工具按「尽力而为」提供，作者不对残留 PHI 承担责任。

## License

MIT
