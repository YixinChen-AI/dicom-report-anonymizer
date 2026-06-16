from anonymizer.core.policy import Policy


def test_default_empty():
    p = Policy()
    assert not p.adds_remove_dicom("Foo")
    assert not p.adds_remove_xml("Foo")
    assert not p.forces_keep("Foo")


def test_extra_remove_case_insensitive():
    p = Policy(extra_remove_dicom={"ProtocolName"}, extra_remove_xml={"ApplyDoctor"})
    assert p.adds_remove_dicom("protocolname")
    assert p.adds_remove_dicom("ProtocolName")
    assert p.adds_remove_xml("applydoctor")


def test_forces_keep_case_insensitive():
    p = Policy(keep={"AccessionNumber"})
    assert p.forces_keep("accessionnumber")
    assert not p.forces_keep("PatientName")


def test_global_keep_applies_to_both_sources():
    """向后兼容：全局 keep 对 DICOM 和 XML 两条链都生效。"""
    p = Policy(keep={"AccessionNumber"})
    assert p.forces_keep_dicom("accessionnumber")
    assert p.forces_keep_xml("accessionnumber")


def test_source_scoped_keep_no_cross_contamination():
    """#4：keep_dicom 只作用 DICOM，不污染 XML 同名字段，反之亦然。"""
    p = Policy(keep_dicom={"AccessionNumber"}, keep_xml={"PatientSex"})
    assert p.forces_keep_dicom("AccessionNumber")
    assert not p.forces_keep_xml("AccessionNumber")
    assert p.forces_keep_xml("PatientSex")
    assert not p.forces_keep_dicom("PatientSex")
    assert p.all_keep() == {"AccessionNumber", "PatientSex"}


def test_json_roundtrip():
    p = Policy(extra_remove_dicom={"A"}, extra_remove_xml={"B"}, keep={"C"},
               keep_dicom={"D"}, keep_xml={"E"}, keep_dates=False)
    p2 = Policy.from_json(p.to_json())
    assert p2.adds_remove_dicom("A")
    assert p2.adds_remove_xml("B")
    assert p2.forces_keep("C")
    assert p2.forces_keep_dicom("D") and not p2.forces_keep_xml("D")
    assert p2.forces_keep_xml("E") and not p2.forces_keep_dicom("E")
    assert p2.keep_dates is False
