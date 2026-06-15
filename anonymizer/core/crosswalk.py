"""真实身份 ↔ 假 ID 对照表。

职责（单一）：把每个患者（以输入文件夹名为主键）映射到一个顺序假 ID
``Patient_000N``，并累积该患者所有真实标识 token（中文名、拼音名、检查号、
DICOM PatientID/PatientName 等），用于：
  - DICOM/XML 去标识时统一替换成同一个假 ID（一致性）；
  - 全文精确替换（XML）与 verify 回扫（找残留真实 PHI）。

明文 CSV 导出/导入（用户自行严格保管，本身是 PHI）。
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

# 进入 secrets() 的 token 最小长度：防止用单字符/单数字做全文替换误伤正文。
MIN_SECRET_LEN = 2


@dataclass
class PatientRecord:
    pseudo_id: str
    folder_name: str
    real_names: set[str] = field(default_factory=set)
    real_ids: set[str] = field(default_factory=set)


class Crosswalk:
    def __init__(self, width: int = 4):
        self.width = width
        self._records: dict[str, PatientRecord] = {}  # key = folder_name
        self._counter = 0

    # ---- 分配 / 查询 ----
    def assign(self, folder_name: str) -> PatientRecord:
        """为某文件夹分配（或返回已分配的）假 ID。幂等。"""
        rec = self._records.get(folder_name)
        if rec is not None:
            return rec
        self._counter += 1
        pseudo = f"Patient_{self._counter:0{self.width}d}"
        rec = PatientRecord(pseudo_id=pseudo, folder_name=folder_name)
        # 文件夹名本身通常就是患者姓名 → 作为一个真实 name token
        if folder_name and folder_name.strip():
            rec.real_names.add(folder_name.strip())
        self._records[folder_name] = rec
        return rec

    def pseudo_for(self, folder_name: str) -> str | None:
        rec = self._records.get(folder_name)
        return rec.pseudo_id if rec else None

    def add_identifiers(self, folder_name: str, names=(), ids=()) -> None:
        """累积某患者的真实标识 token（空/None 忽略）。"""
        rec = self._records.get(folder_name) or self.assign(folder_name)
        for n in names or ():
            if n and str(n).strip():
                rec.real_names.add(str(n).strip())
        for i in ids or ():
            if i and str(i).strip():
                rec.real_ids.add(str(i).strip())

    # ---- secrets（用于替换 / verify）----
    def secrets(self, folder_name: str) -> set[str]:
        rec = self._records.get(folder_name)
        if not rec:
            return set()
        toks = rec.real_names | rec.real_ids
        return {t for t in toks if len(t) >= MIN_SECRET_LEN}

    def all_secrets(self) -> dict[str, str]:
        """所有患者的 token → 假 ID。长 token 优先（避免短 token 抢先匹配）。"""
        mapping: dict[str, str] = {}
        for rec in self._records.values():
            for t in (rec.real_names | rec.real_ids):
                if len(t) >= MIN_SECRET_LEN:
                    mapping[t] = rec.pseudo_id
        return mapping

    def records(self) -> list[PatientRecord]:
        return list(self._records.values())

    # ---- CSV ----
    def to_csv(self, path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        # utf-8-sig 让 Excel 正确识别中文
        with path.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["pseudo_id", "folder_name", "real_names", "real_ids"])
            for rec in self._records.values():
                w.writerow([
                    rec.pseudo_id,
                    rec.folder_name,
                    "|".join(sorted(rec.real_names)),
                    "|".join(sorted(rec.real_ids)),
                ])

    @classmethod
    def from_csv(cls, path, width: int = 4) -> "Crosswalk":
        cw = cls(width=width)
        with Path(path).open("r", newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            max_n = 0
            for row in reader:
                pseudo = row["pseudo_id"]
                folder = row["folder_name"]
                rec = PatientRecord(pseudo_id=pseudo, folder_name=folder)
                rec.real_names = {x for x in row.get("real_names", "").split("|") if x}
                rec.real_ids = {x for x in row.get("real_ids", "").split("|") if x}
                cw._records[folder] = rec
                # 解析编号，保证后续 assign 接着走
                try:
                    n = int(pseudo.rsplit("_", 1)[-1])
                    max_n = max(max_n, n)
                except ValueError:
                    pass
            cw._counter = max_n
        return cw
