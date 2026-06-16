"""xml_deid 测试（TDD）。合成 .NET DataSet 风格 XML（gb2312），非真实数据。"""
from anonymizer.core.policy import Policy
from anonymizer.core.xml_deid import deidentify_xml, harvest_identifiers

SYNTH_XML = """<?xml version="1.0" encoding="gb2312"?>
<NewDataSet>
  <xs:schema id="NewDataSet"><xs:element name="PatientNameC" /></xs:schema>
  <PATIENT>
    <PatientName>TestPinyin</PatientName>
    <PatientNameC>测试名</PatientNameC>
    <PatientID>P99999</PatientID>
    <PatientBirthday>19500101</PatientBirthday>
    <PatientSex>F</PatientSex>
    <PatientAge>070Y</PatientAge>
    <PATIENT_WEIGHT>51.5</PATIENT_WEIGHT>
    <patient_idcard>110101195001010001</patient_idcard>
    <Patient_Address>北京海淀</Patient_Address>
    <StudyInstanceUID>1900000000001</StudyInstanceUID>
    <StudyDate>20190227</StudyDate>
    <ReportingPhysician>张医生</ReportingPhysician>
  </PATIENT>
  <Report>患者测试名，性别女，检查所见正常。</Report>
</NewDataSet>"""


def _bytes():
    return SYNTH_XML.encode("gb2312")


def test_harvest_identifiers():
    ident = harvest_identifiers(_bytes())
    assert "测试名" in ident["names"]
    assert "TestPinyin" in ident["names"]
    assert "P99999" in ident["ids"]
    assert "110101195001010001" in ident["ids"]
    assert "1900000000001" in ident["ids"]


def test_name_and_id_replaced_with_pseudo():
    res = deidentify_xml(_bytes(), "Patient_0001", secrets=["测试名", "TestPinyin", "P99999"])
    t = res.after_text
    assert "<PatientNameC>Patient_0001</PatientNameC>" in t
    assert "<PatientName>Patient_0001</PatientName>" in t
    assert "<PatientID>Patient_0001</PatientID>" in t


def test_phi_fields_blanked():
    res = deidentify_xml(_bytes(), "Patient_0001", secrets=[])
    t = res.after_text
    assert "<PatientBirthday></PatientBirthday>" in t
    assert "<patient_idcard></patient_idcard>" in t
    assert "<Patient_Address></Patient_Address>" in t
    assert "<StudyInstanceUID></StudyInstanceUID>" in t
    assert "<ReportingPhysician></ReportingPhysician>" in t


def test_research_fields_preserved():
    res = deidentify_xml(_bytes(), "Patient_0001", secrets=[])
    t = res.after_text
    assert "<PatientSex>F</PatientSex>" in t
    assert "<PatientAge>070Y</PatientAge>" in t
    assert "<PATIENT_WEIGHT>51.5</PATIENT_WEIGHT>" in t
    assert "<StudyDate>20190227</StudyDate>" in t


def test_report_body_name_scrubbed_via_secrets():
    res = deidentify_xml(_bytes(), "Patient_0001", secrets=["测试名", "TestPinyin"])
    # 报告正文里的真实姓名被替换
    assert "测试名" not in res.after_text


def test_no_real_phi_remains():
    res = deidentify_xml(_bytes(), "Patient_0001",
                         secrets=["测试名", "TestPinyin", "P99999",
                                  "110101195001010001", "1900000000001", "张医生"])
    for token in ["测试名", "TestPinyin", "P99999", "110101195001010001",
                  "1900000000001", "张医生", "北京海淀"]:
        assert token not in res.after_text, f"残留 PHI: {token}"


def test_schema_block_preserved():
    res = deidentify_xml(_bytes(), "Patient_0001", secrets=[])
    # schema 定义里的 element name 不应被当成数据改掉
    assert 'name="PatientNameC"' in res.after_text


def test_output_bytes_decodable():
    res = deidentify_xml(_bytes(), "Patient_0001", secrets=[])
    # 输出可重新按 gb2312 解码，且保留声明
    assert res.output_bytes.decode("gb2312")
    assert "encoding=" in res.after_text


def test_tag_with_attributes_scrubbed():
    xml = ('<?xml version="1.0" encoding="gb2312"?><root>'
           '<PatientNameC lang="zh">测试名</PatientNameC>'
           '<ReportDoctor>张医生</ReportDoctor></root>')
    res = deidentify_xml(xml.encode("gb2312"), "Patient_0001")
    assert "测试名" not in res.after_text       # 带属性标签也被清
    assert "Patient_0001" in res.after_text
    assert "<ReportDoctor></ReportDoctor>" in res.after_text  # 扩充的医生字段被清空


def test_tag_prefix_not_confused():
    # PatientName 不应误伤 PatientNameC（\b 边界）
    xml = ('<?xml version="1.0" encoding="gb2312"?><root>'
           '<PatientName>Pinyin</PatientName><PatientNameC>测试名</PatientNameC></root>')
    res = deidentify_xml(xml.encode("gb2312"), "Patient_0001")
    assert "<PatientName>Patient_0001</PatientName>" in res.after_text
    assert "<PatientNameC>Patient_0001</PatientNameC>" in res.after_text


def test_harvest_collects_doctor_and_address():
    xml = ('<?xml version="1.0" encoding="gb2312"?><PATIENT>'
           '<Patient_Address>北京海淀</Patient_Address>'
           '<ReportingPhysician>张医生</ReportingPhysician></PATIENT>')
    ident = harvest_identifiers(xml.encode("gb2312"))
    assert "北京海淀" in ident["names"]
    assert "张医生" in ident["names"]


def test_policy_extra_remove_xml():
    res = deidentify_xml(_bytes(), "Patient_0001",
                         policy=Policy(extra_remove_xml={"PatientAge"}))
    assert "<PatientAge></PatientAge>" in res.after_text     # 默认保留 → 用户额外删


def test_policy_keep_xml():
    res = deidentify_xml(_bytes(), "Patient_0001",
                         policy=Policy(keep={"PatientBirthday"}))
    assert "<PatientBirthday>19500101</PatientBirthday>" in res.after_text  # 默认删 → 强制保留


def test_single_quote_encoding_decl():
    # 单引号 + 大写编码声明也能正确解码/回写
    xml = ("<?xml version='1.0' encoding='GB2312'?><PATIENT>"
           "<PatientNameC>测试名</PatientNameC></PATIENT>")
    res = deidentify_xml(xml.encode("gb2312"), "Patient_0001")
    assert "测试名" not in res.after_text
    assert res.output_bytes.decode("gb2312")


def test_changes_recorded():
    res = deidentify_xml(_bytes(), "Patient_0001", secrets=[])
    labels = {c[0] for c in res.changes}
    assert "PatientNameC" in labels
    assert "PatientBirthday" in labels
