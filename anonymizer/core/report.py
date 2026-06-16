"""运行报告：聚合本次去标识的统计、失败、需人工复核项、verify 残留。"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Failure:
    file: str
    error: str


@dataclass
class BurnedInFlag:
    patient: str
    file: str
    reason: str


@dataclass
class RunReport:
    input_root: str = ""
    output_root: str = ""
    started: str = ""
    finished: str = ""
    n_patients: int = 0
    n_dicom: int = 0
    n_xml: int = 0
    n_pdf_dropped: int = 0
    n_image_dropped: int = 0
    n_dicom_failed: int = 0
    n_xml_failed: int = 0
    failures: list = field(default_factory=list)        # [Failure]
    burned_in: list = field(default_factory=list)        # [BurnedInFlag]
    leaks: list = field(default_factory=list)            # [verify.Leak]（含"无法验证"项）

    def status(self) -> str:
        """整体状态：FAIL=残留PHI/无法验证；WARN=有失败或疑似烧录；PASS=干净。"""
        if self.leaks:
            return "FAIL"
        if self.n_dicom_failed or self.n_xml_failed or self.burned_in:
            return "WARN"
        return "PASS"

    def to_markdown(self) -> str:
        st = self.status()
        ok = st == "PASS"
        banner = {"PASS": "✅ PASS — 校验通过，未发现残留/失败",
                  "WARN": "⚠️ WARN — 有文件处理失败或疑似烧录，请看下方",
                  "FAIL": "🛑 FAIL — 发现残留 PHI 或无法验证的文件，务必人工复核"}[st]
        lines = [
            "# 去标识运行报告",
            "",
            f"**状态：{banner}**",
            "",
            f"- 输入：`{self.input_root}`",
            f"- 输出：`{self.output_root}`",
            f"- 开始：{self.started}　完成：{self.finished}",
            "",
            "## 统计",
            "",
            f"| 项目 | 数量 |",
            f"|---|---|",
            f"| 患者 | {self.n_patients} |",
            f"| DICOM 去标识 | {self.n_dicom} |",
            f"| XML 报告去标识 | {self.n_xml} |",
            f"| PDF 丢弃 | {self.n_pdf_dropped} |",
            f"| 图片丢弃 | {self.n_image_dropped} |",
            f"| DICOM 失败 | {self.n_dicom_failed} |",
            f"| XML 失败 | {self.n_xml_failed} |",
            "",
            "## 隐私校验（verify 回扫）",
            "",
            ("✅ 未发现任何残留真实姓名/ID。" if ok
             else f"🛑 **发现 {len(self.leaks)} 处疑似残留 PHI，请人工复核！**"),
        ]
        if self.leaks:
            lines += ["", "| 文件 | 类型 | token | 位置 |", "|---|---|---|---|"]
            for lk in self.leaks[:200]:
                lines.append(f"| `{lk.file}` | {lk.kind} | `{lk.token}` | {lk.detail} |")

        if self.burned_in:
            lines += ["", "## ⚠️ 疑似烧录文字（需人工复核 / 可在涂黑界面处理）", "",
                      "| 患者 | 文件 | 原因 |", "|---|---|---|"]
            for b in self.burned_in[:200]:
                lines.append(f"| {b.patient} | `{b.file}` | {b.reason} |")

        if self.failures:
            lines += ["", "## 处理失败", "", "| 文件 | 错误 |", "|---|---|"]
            for fl in self.failures[:200]:
                lines.append(f"| `{fl.file}` | {fl.error} |")

        lines.append("")
        return "\n".join(lines)
