"""编排：扫描 → 建对照表 → 逐患者去标识 → 写输出（丢 PDF/JPG）→ verify 回扫 → 报告。"""
from __future__ import annotations

import datetime
from pathlib import Path

import pydicom

from . import scanner
from . import verify as verify_mod
from .crosswalk import Crosswalk
from .dicom_deid import deidentify_dataset, UidMapper
from .report import BurnedInFlag, Failure, RunReport
from .xml_deid import deidentify_xml, harvest_identifiers


# 输出分两个子目录：可分享的去标识数据 vs 含 PHI 的对照表/报告。
DATA_SUBDIR = "去标识输出_可分享"
PRIVATE_SUBDIR = "_对照表与报告_请勿分享"


def _now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _format_changes(rel: str, changes, extra: str = "") -> str:
    """把单个文件的字段变更格式化成 log 文本块（同一变更去重，重复显示 ×N）。"""
    if not changes and not extra:
        return f"✎ {rel}  （无字段变更）"
    lines = [f"✎ {rel}"]
    counts: dict = {}
    order: list = []
    for label, before, after in changes:
        key = (label, before, after)
        if key not in counts:
            order.append(key)
        counts[key] = counts.get(key, 0) + 1
    for label, before, after in order:
        b = before if len(before) <= 28 else before[:28] + "…"
        n = counts[(label, before, after)]
        suffix = f"  ×{n}" if n > 1 else ""
        lines.append(f"      {label}: {b} → {after if after else '✄清空'}{suffix}")
    if extra:
        lines.append(f"      {extra}")
    return "\n".join(lines)


def _sanitize_relpath(rel: Path, secrets) -> Path:
    toks = sorted((s for s in secrets if s and len(s) >= 2), key=len, reverse=True)
    parts = []
    for part in rel.parts:
        new = part
        for tok in toks:
            if tok in new:
                new = new.replace(tok, "X")
        parts.append(new)
    return Path(*parts) if parts else Path("")


def _build_crosswalk(scan) -> Crosswalk:
    cw = Crosswalk()
    for pg in scan.patients:
        cw.assign(pg.folder_name)
        cw.add_identifiers(pg.folder_name, names=[pg.folder_name])
        for x in pg.xml:
            for piece in x.stem.split("_"):
                if piece.isdigit() and len(piece) >= 4:
                    cw.add_identifiers(pg.folder_name, ids=[piece])
                elif piece and not piece.isdigit() and len(piece) >= 2:
                    cw.add_identifiers(pg.folder_name, names=[piece])
            try:
                ident = harvest_identifiers(x.read_bytes())
                cw.add_identifiers(pg.folder_name, names=ident["names"], ids=ident["ids"])
            except Exception:
                pass
        if pg.dicom:
            try:
                ds = pydicom.dcmread(pg.dicom[0], force=True)
                cw.add_identifiers(pg.folder_name,
                                   names=[str(ds.get("PatientName", ""))],
                                   ids=[str(ds.get("PatientID", ""))])
            except Exception:
                pass
    return cw


def run_pipeline(input_root, output_root, *, progress=None, log=None, keep_dates=True) -> RunReport:
    input_root = Path(input_root)
    output_root = Path(output_root)
    data_root = output_root / DATA_SUBDIR        # 可分享
    private_root = output_root / PRIVATE_SUBDIR   # 含 PHI，勿分享
    data_root.mkdir(parents=True, exist_ok=True)
    private_root.mkdir(parents=True, exist_ok=True)

    scan = scanner.scan(input_root)
    report = RunReport(input_root=str(input_root), output_root=str(data_root), started=_now())
    report.n_patients = len(scan.patients)

    cw = _build_crosswalk(scan)
    mapper = UidMapper()

    total = sum(len(p.dicom) + len(p.xml) for p in scan.patients)
    done = 0

    def tick(msg=""):
        nonlocal done
        done += 1
        if progress:
            progress(done, total, msg)

    for pg in scan.patients:
        pseudo = cw.pseudo_for(pg.folder_name)
        secrets = cw.secrets(pg.folder_name)
        out_pdir = data_root / pseudo

        for i, dcm in enumerate(pg.dicom):
            try:
                ds = pydicom.dcmread(dcm, force=True)
                res = deidentify_dataset(ds, pseudo, mapper,
                                         keep_dates=keep_dates, extra_secrets=secrets)
                subdir = _sanitize_relpath(dcm.relative_to(pg.root).parent, secrets)
                new_name = str(res.dataset.get("SOPInstanceUID", f"{pseudo}_{i:05d}")) + ".dcm"
                target = out_pdir / subdir / new_name
                target.parent.mkdir(parents=True, exist_ok=True)
                res.dataset.save_as(target, enforce_file_format=True)
                report.n_dicom += 1
                if log:
                    extra = f"＋{res.uids_remapped} 个 UID 重映射 · {res.private_removed} 个私有标签移除"
                    log(_format_changes(str(dcm.relative_to(input_root)), res.changes, extra))
                if res.burned_in_suspected:
                    report.burned_in.append(
                        BurnedInFlag(pseudo, str(target), res.burned_in_reason))
            except Exception as e:
                report.n_dicom_failed += 1
                report.failures.append(Failure(str(dcm), repr(e)))
            tick(f"{pseudo} DICOM")

        for j, x in enumerate(pg.xml):
            try:
                res = deidentify_xml(x.read_bytes(), pseudo, secrets=secrets)
                target = out_pdir / f"{pseudo}_{j}.xml"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(res.output_bytes)
                report.n_xml += 1
                if log:
                    log(_format_changes(str(x.relative_to(input_root)), res.changes))
            except Exception as e:
                report.n_xml_failed += 1
                report.failures.append(Failure(str(x), repr(e)))
            tick(f"{pseudo} XML")

        report.n_pdf_dropped += len(pg.pdf)
        report.n_image_dropped += len(pg.image)

    # 对照表 + 报告写入私密子目录（含 PHI，绝不随去标识数据分享）
    cw.to_csv(private_root / "crosswalk.csv")
    # 只回扫可分享的去标识数据
    report.leaks = verify_mod.verify_output_tree(data_root, list(cw.all_secrets().keys()))
    report.finished = _now()
    (private_root / "run_report.md").write_text(report.to_markdown(), encoding="utf-8")

    if progress and total == 0:
        progress(0, 0, "无可处理文件")
    return report
