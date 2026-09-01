"""HuanyuApiError 属性与消息行为测试。"""
from huanyu_sdk.exceptions import HuanyuApiError


def test_attributes_and_str():
    # code/time 来自平台响应信封；str(e) 只给业务消息，不拼元组
    err = HuanyuApiError("商户单号已存在", 0, 1756684900)
    assert err.api_code == 0
    assert err.api_time == 1756684900
    assert str(err) == "商户单号已存在"


def test_api_time_defaults_to_none():
    err = HuanyuApiError("签名错误", 1001)
    assert err.api_code == 1001
    assert err.api_time is None
