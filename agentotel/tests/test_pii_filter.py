"""PII 脱敏测试。"""

from agentotel.plugins.pii_filter import mask_text, PIIFilterPlugin


def test_phone_in_chinese():
    out = mask_text("我手机是13812345678。")
    assert "13812345678" not in out
    assert "***PHONE***" in out


def test_id_card_in_chinese():
    out = mask_text("身份证110101199003078888。")
    assert "110101199003078888" not in out
    assert "***ID_CARD***" in out


def test_email():
    out = mask_text("邮箱 a@b.com 谢谢")
    assert "a@b.com" not in out
    assert "***EMAIL***" in out


def test_bank_card():
    out = mask_text("卡号6222021234567890123")
    assert "6222021234567890123" not in out


def test_combined():
    out = mask_text("手机13812345678，身份证110101199003078888，邮箱a@b.com")
    assert "***PHONE***" in out
    assert "***ID_CARD***" in out
    assert "***EMAIL***" in out


def test_plugin_passes_non_string():
    plugin = PIIFilterPlugin()
    out = plugin.process(None, {"n": 1, "b": True})
    assert out["n"] == 1 and out["b"] is True


def test_plugin_handles_string_list():
    plugin = PIIFilterPlugin()
    out = plugin.process(None, {"arr": ["13812345678", "x"]})
    assert out["arr"][0] == "***PHONE***"
