"""Signature 向量驱动测试。

向量真源（由后端参考实现生成，向量即真理）：
- common/vectors/signature_vectors.json：请求签名，7 例
- common/vectors/callback_vectors.json：回调验签，2 例
"""
import hashlib
import json
from pathlib import Path

import pytest

from huanyu_sdk.signature import php_json, sign

VECTORS_DIR = Path(__file__).resolve().parent.parent / "common" / "vectors"

# U+2028/U+2029 是不可见的行/段分隔符，用 chr() 构造，避免源码文件中出现裸字符
LINE_SEPARATOR = chr(0x2028)
PARAGRAPH_SEPARATOR = chr(0x2029)


def _load_cases(filename):
    """读取向量文件，展开为 pytest 参数（id 取用例 id，便于失败定位）。"""
    with open(VECTORS_DIR / filename, encoding="utf-8") as f:
        data = json.load(f)
    return [
        pytest.param(
            data["api_secret"],
            case["params"],
            case["expected_signature"],
            id=case["id"],
        )
        for case in data["cases"]
    ]


@pytest.mark.parametrize(
    "api_secret,params,expected", _load_cases("signature_vectors.json")
)
def test_sign_matches_signature_vectors(api_secret, params, expected):
    """请求签名：spec/signature.md 六步的结果必须与后端实测向量一致。"""
    assert sign(params, api_secret) == expected


@pytest.mark.parametrize(
    "api_secret,params,expected", _load_cases("callback_vectors.json")
)
def test_sign_matches_callback_vectors(api_secret, params, expected):
    """回调验签：同一算法重算签名，与回调数据携带的 signature 比对。"""
    assert sign(params, api_secret) == expected


class TestPhpJson:
    """php_json 的 PHP json_encode 兼容行为逐项锁定。"""

    def test_slash_escaped_as_backslash_slash(self):
        # PHP json_encode 默认转义 /，Python json.dumps 不转义，需补齐
        assert php_json({"sub_bank": "http测试支行/分行"}) == (
            '{"sub_bank":"http测试支行\\/分行"}'
        )

    def test_chinese_not_escaped(self):
        # JSON_UNESCAPED_UNICODE 语义：非 ASCII 原样输出
        assert php_json({"name": "张三"}) == '{"name":"张三"}'

    def test_no_spaces_and_insertion_order_preserved(self):
        # 分隔符无空格，键按插入序（不排序）
        assert php_json({"b": 1, "a": 2}) == '{"b":1,"a":2}'

    def test_line_and_paragraph_separator_escaped(self):
        # U+2028/U+2029 是 PHP json_encode 固有转义（即使 UNESCAPED_UNICODE）
        assert php_json({"v": "a" + LINE_SEPARATOR + "b" + PARAGRAPH_SEPARATOR + "c"}) == (
            '{"v":"a\\u2028b\\u2029c"}'
        )

    def test_slash_and_line_separator_chain(self):
        # 锁定替换链：先转义 /，再转义 U+2028，两步互不干扰
        assert php_json({"v": "/" + LINE_SEPARATOR}) == '{"v":"\\/\\u2028"}'

    def test_control_chars_escaped(self):
        # 控制字符按 JSON 标准转义（\n \t）
        assert php_json({"v": "a\nb\tc"}) == '{"v":"a\\nb\\tc"}'

    def test_html_chars_not_escaped(self):
        # < > & 输出原始字符，不做 HTML 转义（与 Go 默认行为不同）
        assert php_json({"v": "<b>&"}) == '{"v":"<b>&"}'

    def test_quote_and_backslash_escaped(self):
        assert php_json({"v": '"\\'}) == '{"v":"\\"\\\\"}'

    def test_literal_backslash_u_sequence_untouched(self):
        # 输入值本身含 "\u2028" 字面（反斜杠+u2028）：json.dumps 输出 \\u2028，
        # U+2028 字符替换按真实字符匹配，不会误伤该字面形态
        assert php_json({"v": "\\u2028"}) == '{"v":"\\\\u2028"}'


class TestSignEdgeCases:
    def test_zero_and_false_are_signed(self):
        # 空值判断用显式 is not None / != ""，0 与 False 必须参与签名
        # （对照 PHP $value !== '' && $value !== null）
        raw = "&".join(["a=0", "b=False"]) + "&api_secret=s"

        assert sign({"a": 0, "b": False}, "s") == hashlib.md5(
            raw.encode("utf-8")
        ).hexdigest().upper()

    def test_empty_params_still_signs_secret(self):
        # 全部参数为空：拼串为空后仍追加 &api_secret=（与 PHP rtrim 行为一致）
        assert sign({"remark": "", "extra": None}, "s") == hashlib.md5(
            b"&api_secret=s"
        ).hexdigest().upper()
