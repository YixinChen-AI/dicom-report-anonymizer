import pydicom

from anonymizer.core.pipeline import run_pipeline
from tests._synth import write_synth_dataset


def test_pipeline_end_to_end(tmp_path):
    src = write_synth_dataset(tmp_path / "ds")
    out = tmp_path / "out"
    report = run_pipeline(src, out)

    # 两个患者，假 ID 顺序
    assert (out / "Patient_0001").is_dir()
    assert (out / "Patient_0002").is_dir()

    # DICOM 去标识后存在
    dcms = list(out.rglob("*.dcm"))
    assert len(dcms) == 4
    ds = pydicom.dcmread(dcms[0])
    assert str(ds.PatientName).startswith("Patient_")
    assert ds.PatientID.startswith("Patient_")
    assert ds.PatientBirthDate == ""

    # XML 去标识后存在
    xmls = list(out.rglob("*.xml"))
    assert len(xmls) == 2

    # PDF/JPG 不进输出
    assert list(out.rglob("*.pdf")) == []
    assert list(out.rglob("*.jpg")) == []

    # 对照表生成
    assert (out / "crosswalk.csv").exists()


def test_pipeline_no_phi_leak(tmp_path):
    src = write_synth_dataset(tmp_path / "ds")
    out = tmp_path / "out"
    report = run_pipeline(src, out)
    # verify 兜底：输出里不应残留任何真实姓名/ID
    assert report.leaks == [], f"残留 PHI: {report.leaks}"


def test_pipeline_report_counts(tmp_path):
    src = write_synth_dataset(tmp_path / "ds")
    out = tmp_path / "out"
    report = run_pipeline(src, out)
    assert report.n_patients == 2
    assert report.n_dicom == 4
    assert report.n_xml == 2
    assert report.n_pdf_dropped == 2
    assert report.n_image_dropped == 2
    md = report.to_markdown()
    assert "Patient" in md or "患者" in md


def test_pipeline_progress_callback(tmp_path):
    src = write_synth_dataset(tmp_path / "ds")
    out = tmp_path / "out"
    seen = []
    run_pipeline(src, out, progress=lambda done, total, msg: seen.append((done, total)))
    assert seen
    assert seen[-1][0] == seen[-1][1]   # 最终 done == total
