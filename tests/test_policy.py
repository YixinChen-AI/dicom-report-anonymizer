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


def test_json_roundtrip():
    p = Policy(extra_remove_dicom={"A"}, extra_remove_xml={"B"}, keep={"C"}, keep_dates=False)
    p2 = Policy.from_json(p.to_json())
    assert p2.adds_remove_dicom("A")
    assert p2.adds_remove_xml("B")
    assert p2.forces_keep("C")
    assert p2.keep_dates is False
