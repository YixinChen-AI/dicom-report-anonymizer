"""极简去标识策略：在内置默认规则之上，让用户【额外指定要清空的标签】或
【把某个默认清空的标签强制保留】。默认空策略 == 现有行为（向后兼容）。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass
class Policy:
    extra_remove_dicom: set = field(default_factory=set)   # 额外清空的 DICOM keyword
    extra_remove_xml: set = field(default_factory=set)     # 额外清空的 XML 字段名
    keep: set = field(default_factory=set)                 # 强制保留(覆盖默认清空)，DICOM/XML 通用
    keep_dates: bool = True

    # ---- 查询（大小写不敏感）----
    def adds_remove_dicom(self, keyword: str) -> bool:
        return bool(keyword) and keyword.lower() in self._lc(self.extra_remove_dicom)

    def adds_remove_xml(self, tag: str) -> bool:
        return bool(tag) and tag.lower() in self._lc(self.extra_remove_xml)

    def forces_keep(self, name: str) -> bool:
        return bool(name) and name.lower() in self._lc(self.keep)

    @staticmethod
    def _lc(names) -> set:
        return {str(n).lower() for n in names}

    # ---- 序列化（用于策略模板存/载 + 审计）----
    def to_dict(self) -> dict:
        return {
            "extra_remove_dicom": sorted(self.extra_remove_dicom),
            "extra_remove_xml": sorted(self.extra_remove_xml),
            "keep": sorted(self.keep),
            "keep_dates": self.keep_dates,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, d: dict) -> "Policy":
        return cls(
            extra_remove_dicom=set(d.get("extra_remove_dicom", [])),
            extra_remove_xml=set(d.get("extra_remove_xml", [])),
            keep=set(d.get("keep", [])),
            keep_dates=bool(d.get("keep_dates", True)),
        )

    @classmethod
    def from_json(cls, s: str) -> "Policy":
        return cls.from_dict(json.loads(s))


DEFAULT_POLICY = Policy()
