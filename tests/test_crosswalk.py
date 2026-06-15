"""crosswalk 模块测试（先写测试，TDD）。"""
from anonymizer.core.crosswalk import Crosswalk


def test_assign_sequential():
    cw = Crosswalk()
    assert cw.assign("万学中").pseudo_id == "Patient_0001"
    assert cw.assign("乔金庄").pseudo_id == "Patient_0002"
    assert cw.assign("关秀清").pseudo_id == "Patient_0003"


def test_assign_idempotent():
    cw = Crosswalk()
    first = cw.assign("万学中")
    again = cw.assign("万学中")
    assert first.pseudo_id == again.pseudo_id == "Patient_0001"
    # 重复 assign 不消耗新编号
    assert cw.assign("乔金庄").pseudo_id == "Patient_0002"


def test_pseudo_for():
    cw = Crosswalk()
    cw.assign("万学中")
    assert cw.pseudo_for("万学中") == "Patient_0001"
    assert cw.pseudo_for("不存在") is None


def test_add_identifiers_and_secrets():
    cw = Crosswalk()
    cw.assign("万学中")
    cw.add_identifiers("万学中", names=["万学中", "WanXueZhong", ""], ids=["1902263576795", None])
    secrets = cw.secrets("万学中")
    assert "万学中" in secrets
    assert "WanXueZhong" in secrets
    assert "1902263576795" in secrets
    # 空/None 被忽略
    assert "" not in secrets
    assert None not in secrets


def test_secrets_filters_too_short_tokens():
    cw = Crosswalk()
    cw.assign("X")
    cw.add_identifiers("X", names=["王", "李明"], ids=["7"])
    secrets = cw.secrets("X")
    # 单字符 token 不进 secrets（防全文替换误伤），>=2 字符保留
    assert "王" not in secrets
    assert "7" not in secrets
    assert "李明" in secrets


def test_all_secrets_maps_token_to_pseudo():
    cw = Crosswalk()
    cw.assign("万学中")
    cw.add_identifiers("万学中", names=["万学中"], ids=["1902263576795"])
    cw.assign("乔金庄")
    cw.add_identifiers("乔金庄", names=["乔金庄"], ids=["2202284609059"])
    mapping = cw.all_secrets()
    assert mapping["万学中"] == "Patient_0001"
    assert mapping["1902263576795"] == "Patient_0001"
    assert mapping["乔金庄"] == "Patient_0002"


def test_csv_roundtrip(tmp_path):
    cw = Crosswalk()
    cw.assign("万学中")
    cw.add_identifiers("万学中", names=["万学中", "WanXueZhong"], ids=["1902263576795"])
    cw.assign("乔金庄")
    cw.add_identifiers("乔金庄", names=["乔金庄"], ids=["2202284609059"])
    path = tmp_path / "crosswalk.csv"
    cw.to_csv(path)

    loaded = Crosswalk.from_csv(path)
    assert loaded.pseudo_for("万学中") == "Patient_0001"
    assert loaded.pseudo_for("乔金庄") == "Patient_0002"
    assert "WanXueZhong" in loaded.secrets("万学中")
    assert "1902263576795" in loaded.secrets("万学中")
    # 往返后继续 assign 新患者，编号接着走
    assert loaded.assign("新患者").pseudo_id == "Patient_0003"


def test_configurable_width():
    cw = Crosswalk(width=3)
    assert cw.assign("a").pseudo_id == "Patient_001"
