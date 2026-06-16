"""安全网：回扫去标识输出，发现任何残留真实 PHI token 立即报告。

注意：crosswalk.csv / 运行报告 等本就允许含真实信息的文件不参与扫描。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pydicom

# 这些文件本就允许含真实 PHI，不算 leak。
IGNORE_NAMES = {"crosswalk.csv", "run_report.md", "run_report.html", "run_report.txt"}

# 启发式残留 PHI 正则（即使未进 secrets 也能报警）：中国身份证 18 位、大陆手机 11 位。
# 边界用「前后不能是字母或数字」：避免误匹配嵌在文件名/UID 等字母数字串里的数字段。
PHI_REGEXES = [
    ("身份证号", re.compile(r"(?<![0-9A-Za-z])\d{17}[\dXx](?![0-9A-Za-z])")),
    ("手机号", re.compile(r"(?<![0-9A-Za-z])1[3-9]\d{9}(?![0-9A-Za-z])")),
]


@dataclass
class Leak:
    file: str
    kind: str       # "dicom" | "text"
    token: str
    detail: str


def _meaningful(secrets) -> list[str]:
    return sorted({str(s) for s in secrets if s and len(str(s)) >= 2}, key=len, reverse=True)


def _regex_hits(text: str) -> list:
    out = []
    for label, rx in PHI_REGEXES:
        m = rx.search(text)
        if m:
            i = m.start()
            out.append((label, text[max(0, i - 20):i + len(m.group()) + 20]))
    return out


def verify_text(text: str, secrets) -> list:
    found = []
    for tok in _meaningful(secrets):
        idx = text.find(tok)
        if idx >= 0:
            found.append((tok, text[max(0, idx - 20):idx + len(tok) + 20]))
    found.extend(_regex_hits(text))
    return found


def verify_dicom_file(path, secrets) -> list:
    found = []
    toks = _meaningful(secrets)
    try:
        ds = pydicom.dcmread(path, force=True)
    except Exception as e:  # noqa: BLE001 — 坏文件不能当作安全，标为无法验证
        return [("<读取失败>", f"<无法验证: {type(e).__name__}>")]
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
        for label, rx in PHI_REGEXES:
            if rx.search(val):
                found.append((str(elem.tag), label))
    return found


def verify_output_tree(output_root, secrets, ignore=IGNORE_NAMES) -> list:
    """回扫整个输出：.dcm 查标签，其余按文本解码后查（已知 token + 启发式正则）。

    未知扩展名也尝试文本扫描（fail-closed）；只有解不出文本的二进制（如图片）才跳过。
    """
    output_root = Path(output_root)
    leaks: list = []
    toks = _meaningful(secrets)
    for f in output_root.rglob("*"):
        if not f.is_file() or f.name in ignore:
            continue
        if f.suffix.lower() == ".dcm":
            for tag, tok in verify_dicom_file(f, toks):
                leaks.append(Leak(file=str(f), kind="dicom", token=tok, detail=tag))
            continue
        try:
            raw = f.read_bytes()
        except OSError:
            continue
        text = None
        for codec in ("utf-8", "gbk"):   # 不用 latin-1，避免二进制乱码误报
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
