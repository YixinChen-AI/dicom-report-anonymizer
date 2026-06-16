from anonymizer.core.report import RunReport
from anonymizer.core.verify import Leak


def test_status_pass():
    assert RunReport().status() == "PASS"


def test_status_fail_on_leak():
    r = RunReport(leaks=[Leak("f.dcm", "text", "万学中", "ctx")])
    assert r.status() == "FAIL"
    assert "FAIL" in r.to_markdown()


def test_status_warn_on_failure():
    r = RunReport(n_dicom_failed=1)
    assert r.status() == "WARN"          # 有失败 → 不能报 PASS
    assert "WARN" in r.to_markdown()


def test_status_warn_on_burned_in():
    from anonymizer.core.report import BurnedInFlag
    r = RunReport(burned_in=[BurnedInFlag("P1", "f.dcm", "SC")])
    assert r.status() == "WARN"
