"""CallbackVerifier 回调验签测试。

向量真源：common/vectors/callback_vectors.json（2 例，向量即真理）。
入参为 application/x-www-form-urlencoded body 解析出的键值对（含 signature）。
"""
import json
from pathlib import Path

import pytest

from huanyu_sdk.callback_verifier import CallbackVerifier

VECTORS_FILE = Path(__file__).resolve().parent.parent / "common" / "vectors" / "callback_vectors.json"


def _load_cases():
    with open(VECTORS_FILE, encoding="utf-8") as f:
        data = json.load(f)
    return data["api_secret"], data["cases"]


API_SECRET, CASES = _load_cases()


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_verify_accepts_callback_vectors(case):
    """回调向量 ×2：携带正确 signature 的回调数据验签通过。"""
    payload = {**case["params"], "signature": case["expected_signature"]}
    assert CallbackVerifier(API_SECRET).verify(payload) is True


def test_verify_rejects_tampered_cny_amount():
    """篡改 cny_amount 后重算签名不再匹配，必须拒绝。"""
    case = CASES[0]
    payload = {**case["params"], "cny_amount": "99999.00", "signature": case["expected_signature"]}
    assert CallbackVerifier(API_SECRET).verify(payload) is False


def test_verify_rejects_missing_signature():
    """缺 signature 字段直接返回 False（不抛异常、不参与签名计算成功）。"""
    assert CallbackVerifier(API_SECRET).verify(dict(CASES[0]["params"])) is False


def test_verify_rejects_empty_signature():
    """signature 为空串同样拒绝。"""
    payload = {**CASES[0]["params"], "signature": ""}
    assert CallbackVerifier(API_SECRET).verify(payload) is False
