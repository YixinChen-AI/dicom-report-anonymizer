"""扫描输入目录，按患者分组并分类文件。"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

DICOM_EXT = {".dcm", ".ima"}   # .ima = Siemens DICOM 常见扩展
XML_EXT = {".xml"}
PDF_EXT = {".pdf"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}


@dataclass
class PatientGroup:
    folder_name: str
    root: Path
    dicom: list = field(default_factory=list)
    xml: list = field(default_factory=list)
    pdf: list = field(default_factory=list)
    image: list = field(default_factory=list)
    other: list = field(default_factory=list)


@dataclass
class ScanResult:
    root: Path
    root_name: str
    patients: list = field(default_factory=list)
    master_files: list = field(default_factory=list)   # 顶层散文件（如 .xls 总表）


def _looks_like_dicom(path: Path) -> bool:
    if path.suffix.lower() in DICOM_EXT:
        return True
    if path.suffix == "":   # 无扩展名 → 嗅探 DICM magic
        try:
            with path.open("rb") as f:
                f.seek(128)
                return f.read(4) == b"DICM"
        except OSError:
            return False
    return False


def _classify_into(pg: PatientGroup, path: Path) -> None:
    ext = path.suffix.lower()
    if _looks_like_dicom(path):
        pg.dicom.append(path)
    elif ext in XML_EXT:
        pg.xml.append(path)
    elif ext in PDF_EXT:
        pg.pdf.append(path)
    elif ext in IMAGE_EXT:
        pg.image.append(path)
    else:
        pg.other.append(path)


def scan(root) -> ScanResult:
    """把所选目录的子目录视为患者，顶层散文件视为总表类文件。

    不做"单子目录自动下钻"的脆弱猜测——由 UI 展示检测到的患者数让用户确认层级。
    """
    root = Path(root)
    res = ScanResult(root=root, root_name=root.name)

    for child in sorted(root.iterdir(), key=lambda p: p.name):
        if child.is_dir():
            pg = PatientGroup(folder_name=child.name, root=child)
            for f in sorted(child.rglob("*")):
                if f.is_file():
                    _classify_into(pg, f)
            res.patients.append(pg)
        elif child.is_file():
            res.master_files.append(child)

    res.patients.sort(key=lambda p: p.folder_name)
    return res
