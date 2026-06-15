"""安全网：回扫去标识输出，发现任何残留真实 PHI token 立即报告。

注意：crosswalk.csv / 运行报告 等本就允许含真实信息的文件不参与扫描。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pydicom

# 这些文件本就允许含真实 PHI，不算 leak。
IGNORE_NAMES = {"crosswalk.csv", "run_report.md", "run_report.html", "run_report.txt"}

_SCAN_EXT = {".xml", ".txt", ".json", ".dcm"}


@dataclass
class Leak:
    file: str
    kind: str       # "dicom" | "text"
    token: str
    detail: str


def _meaningful(secrets) -> list[str]:
    return sorted({str(s) for s in secrets if s and len(str(s)) >= 2}, key=len, reverse=True)


def verify_text(text: str, secrets) -> list:
    found = []
    for tok in _meaningful(secrets):
        idx = text.find(tok)
        if idx >= 0:
            found.append((tok, text[max(0, idx - 20):idx + len(tok) + 20]))
    return found


def verify_dicom_file(path, secrets) -> list:
    found = []
    toks = _meaningful(secrets)
    try:
        ds = pydicom.dcmread(path, force=True)
    except Exception:
        return found
    for elem in ds.iterall():
        if elem.VR in ("OB", "OW", "OF", "OD", "UN", "SQ"):
            continue
        try:
            val = str(elem.value)
        except Exception:
            continue
        for tok in toks:
            if tok in val:
                found.append((str(elem.tag), tok))
    return found


def verify_output_tree(output_root, secrets, ignore=IGNORE_NAMES) -> list:
    output_root = Path(output_root)
    leaks: list = []
    toks = _meaningful(secrets)
    if not toks:
        return leaks
    for f in output_root.rglob("*"):
        if not f.is_file() or f.name in ignore:
            continue
        ext = f.suffix.lower()
        if ext == ".dcm":
            for tag, tok in verify_dicom_file(f, toks):
                leaks.append(Leak(file=str(f), kind="dicom", token=tok, detail=tag))
        elif ext in _SCAN_EXT:
            try:
                raw = f.read_bytes()
            except OSError:
                continue
            text = None
            for codec in ("utf-8", "gbk", "latin-1"):
                try:
                    text = raw.decode(codec)
                    break
                except UnicodeDecodeError:
                    continue
            if text is None:
                continue
            for tok, ctx in verify_text(text, toks):
                leaks.append(Leak(file=str(f), kind="text", token=tok, detail=ctx))
    return leaks
