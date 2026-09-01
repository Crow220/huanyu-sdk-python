"""Client 测试（responses 拦截 HTTP，零真实网络）。

断言三层：
1. 上行形态——嵌套参数括号记法展平、None 不上行（空串照常上行）、白名单过滤、通用参数注入；
2. 签名对齐——服务端视角把扁平表单重嵌套后用同一 Signature.sign 重算，必须与上行签名一致；
3. 响应信封——code!=1 抛 HuanyuApiError，非 200 / 非 JSON / 缺 code 抛 RuntimeError。
"""
from urllib.parse import parse_qs, urlparse

import requests
import responses

from huanyu_sdk.client import Client, DEFAULT_BASE_URL
from huanyu_sdk.exceptions import HuanyuApiError
from huanyu_sdk.signature import sign

API_KEY = "test-key-0001"
API_SECRET = "test-secret-0001"
BASE = "https://api.example.test"


def make_client():
    return Client(API_KEY, API_SECRET, base_url=BASE)


def _form_of(request) -> dict:
    """POST body → {key: [values]}；keep_blank_values 保留空值便于断言“未上行”。"""
    body = request.body
    if isinstance(body, bytes):
        body = body.decode("utf-8")
    return parse_qs(body, keep_blank_values=True)


def _query_of(request) -> dict:
    return parse_qs(urlparse(request.url).query, keep_blank_values=True)


def _flat_items(parsed: dict) -> dict:
    return {k: v[0] for k, v in parsed.items()}


def _renest(flat: dict) -> dict:
    """把 payment_method[bank] 形态还原为嵌套 dict（模拟服务端 parse_str，保持首现插入序）。"""
    nested = {}
    for key, value in flat.items():
        if "[" in key:
            head, rest = key.split("[", 1)
            nested.setdefault(head, {})[rest[:-1]] = value
        else:
            nested[key] = value
    return nested


class TestClientDefaults:
    def test_default_base_url(self):
        assert DEFAULT_BASE_URL == "https://api.pisces-pay.cn/addons/huanyu"
        assert Client(API_KEY, API_SECRET).base_url == DEFAULT_BASE_URL
        assert Client(API_KEY, API_SECRET).timeout == 30

    def test_base_url_strips_trailing_slash(self):
        assert Client(API_KEY, API_SECRET, base_url="https://x.test/prefix/").base_url == "https://x.test/prefix"

    def test_session_injection(self):
        session = requests.Session()
        client = Client(API_KEY, API_SECRET, session=session)
        assert client.session is session


class TestCreateOrder:
    @responses.activate
    def test_nested_payment_method_flattened_and_signature_roundtrip(self):
        """乱序嵌套 payment_method：括号记法展平上行、无 dict-str 垃圾值、服务端重嵌套后重算签名一致。"""
        responses.post(
            f"{BASE}/merchant/createOrder",
            json={"code": 1, "msg": "ok", "data": {"order_no": "HY001", "result_status": "success"}, "time": 1756684900},
        )
        # 乱序 dict：插入序 ≠ 字典序，锁定“按插入序展平”（服务端重嵌套键序才能与签名 JSON 化一致）
        payment_method = {
            "real_name": "张三",
            "card_number": "6222020000000000000",
            "bank": "工商银行",
            "sub_bank": "http测试支行/分行",
        }
        result = make_client().create_order({
            "order_type": 2,
            "cny_amount": "500.50",
            "payment_method": payment_method,
            "merchant_order_no": "M001",
            "ignore_me": "白名单外字段",
        })
        assert result["result_status"] == "success"

        request = responses.calls[0].request
        form = _form_of(request)

        # 扁平键存在且值正确
        assert form["payment_method[real_name]"] == ["张三"]
        assert form["payment_method[card_number]"] == ["6222020000000000000"]
        assert form["payment_method[bank]"] == ["工商银行"]
        assert form["payment_method[sub_bank]"] == ["http测试支行/分行"]
        # 绝不出现 dict 被 str() 成 "{...}" 的垃圾值
        for values in form.values():
            for value in values:
                assert not value.startswith("{")
        # 白名单外字段不上行
        assert "ignore_me" not in form
        # 通用参数注入：api_key / 秒级 timestamp / 16 位 nonce
        assert form["api_key"] == [API_KEY]
        assert len(form["timestamp"][0]) == 10 and form["timestamp"][0].isdigit()
        assert len(form["nonce"][0]) == 16

        # 服务端视角：重嵌套 → 同一算法重算 → 与上行签名比对
        received = _renest(_flat_items(form))
        signature = received.pop("signature")
        assert received["payment_method"] == {
            "real_name": "张三",
            "card_number": "6222020000000000000",
            "bank": "工商银行",
            "sub_bank": "http测试支行/分行",
        }
        assert sign(received, API_SECRET) == signature

    @responses.activate
    def test_nested_empty_string_leaf_roundtrip(self):
        """嵌套空串叶子（sub_bank 未填）必须上行空值键：服务端重嵌套后 json_encode
        保住该键，与客户端签名时的 JSON 形态一致。修复前展平跳过空串 → 服务端
        重嵌套缺键 → 签名重算不一致 → 拒签。"""
        responses.post(
            f"{BASE}/merchant/createOrder",
            json={"code": 1, "msg": "ok", "data": {"order_no": "HY003", "result_status": "success"}, "time": 1756684900},
        )
        payment_method = {
            "bank": "工商银行",
            "sub_bank": "",
            "card_number": "6222020200112233445",
            "real_name": "张三",
        }
        result = make_client().create_order({
            "order_type": "2",
            "cny_amount": "500.50",
            "payment_method": payment_method,
            "merchant_order_no": "M003",
        })
        assert result["result_status"] == "success"

        form = _form_of(responses.calls[0].request)
        # 空值扁平键必须确实上行（keep_blank_values 保留空值，可与“键缺失”区分）
        assert form.get("payment_method[sub_bank]") == [""]

        received = _renest(_flat_items(form))
        signature = received.pop("signature")
        assert received["payment_method"]["sub_bank"] == ""
        assert sign(received, API_SECRET) == signature

    @responses.activate
    def test_pending_identity_branch(self):
        """code=1 且 result_status=pending_identity：正常返回 data（含 identity_url）。"""
        responses.post(
            f"{BASE}/merchant/createOrder",
            json={"code": 1, "msg": "ok", "data": {"result_status": "pending_identity", "identity_url": "https://verify.example.test/id"}, "time": 1756684900},
        )
        result = make_client().create_order({"order_type": 1, "cny_amount": "100.00"})
        assert result == {"result_status": "pending_identity", "identity_url": "https://verify.example.test/id"}


class TestErrorEnvelope:
    @responses.activate
    def test_code_not_one_raises_huanyu_api_error(self):
        """code=0：抛 HuanyuApiError，api_code / str / api_time 逐项断言。"""
        responses.post(
            f"{BASE}/merchant/createOrder",
            json={"code": 0, "msg": "商户单号已存在", "time": 1756684900},
        )
        try:
            make_client().create_order({"order_type": 1, "cny_amount": "100.00"})
        except HuanyuApiError as e:
            assert e.api_code == 0
            assert str(e) == "商户单号已存在"
            assert e.api_time == 1756684900
        else:
            raise AssertionError("code=0 必须抛 HuanyuApiError")

    @responses.activate
    def test_non_200_raises_runtime_error_with_snippet(self):
        responses.post(f"{BASE}/merchant/createOrder", body="Internal Server Error", status=500)
        try:
            make_client().create_order({"order_type": 1, "cny_amount": "1"})
        except RuntimeError as e:
            assert "500" in str(e)
            assert "Internal Server Error" in str(e)
        else:
            raise AssertionError("非 200 必须抛 RuntimeError")

    @responses.activate
    def test_invalid_json_raises_runtime_error_with_truncated_snippet(self):
        # 超长非 JSON 响应体：错误信息截断至 200 字符（对齐 PHP substr($body, 0, 200)）
        responses.post(f"{BASE}/merchant/createOrder", body="x" * 300)
        try:
            make_client().create_order({"order_type": 1, "cny_amount": "1"})
        except RuntimeError as e:
            assert "x" * 200 in str(e)
            assert "x" * 201 not in str(e)
        else:
            raise AssertionError("非 JSON 必须抛 RuntimeError")

    @responses.activate
    def test_missing_code_raises_runtime_error(self):
        responses.post(f"{BASE}/merchant/createOrder", json={"msg": "no code field"})
        try:
            make_client().create_order({"order_type": 1, "cny_amount": "1"})
        except RuntimeError as e:
            assert "no code field" in str(e)
        else:
            raise AssertionError("缺 code 必须抛 RuntimeError")

    @responses.activate
    def test_null_data_returns_empty_dict(self):
        responses.post(f"{BASE}/merchant/createOrder", json={"code": 1, "msg": "ok", "data": None})
        assert make_client().create_order({"order_type": 1, "cny_amount": "1"}) == {}


class TestGetEndpoints:
    @responses.activate
    def test_order_detail_get_query_carries_order_no_and_signature(self):
        """GET：query 含 order_no 与 signature，白名单外字段过滤，服务端视角重算签名一致。"""
        responses.get(
            f"{BASE}/merchant/orderDetailApi",
            json={"code": 1, "msg": "ok", "data": {"order_no": "HY001", "status": "pending"}, "time": 1756684900},
        )
        result = make_client().order_detail({"order_no": "HY001", "extra": "白名单外"})
        assert result["order_no"] == "HY001"

        query = _query_of(responses.calls[0].request)
        assert query["order_no"] == ["HY001"]
        assert "extra" not in query
        received = _flat_items(query)
        signature = received.pop("signature")
        assert sign(received, API_SECRET) == signature

    @responses.activate
    def test_order_list_whitelist_and_get(self):
        responses.get(
            f"{BASE}/merchant/orderListApi",
            json={"code": 1, "msg": "ok", "data": {"list": [], "total": 0, "page": 2, "limit": 50, "status_counts": {}}, "time": 1756684900},
        )
        result = make_client().order_list({"page": 2, "limit": 50, "keyword": "白名单外"})
        assert result["total"] == 0

        query = _query_of(responses.calls[0].request)
        assert query["page"] == ["2"]
        assert query["limit"] == ["50"]
        assert "keyword" not in query

    @responses.activate
    def test_order_list_none_filters_defaults_to_empty(self):
        responses.get(f"{BASE}/merchant/orderListApi", json={"code": 1, "msg": "ok", "data": {"total": 0}, "time": 1756684900})
        assert make_client().order_list() == {"total": 0}
        query = _query_of(responses.calls[0].request)
        assert set(query) == {"api_key", "timestamp", "nonce", "signature"}


class TestPostEndpoints:
    @responses.activate
    def test_upload_payment_proof_sends_both_fields(self):
        responses.post(
            f"{BASE}/merchant/uploadPaymentProof",
            json={"code": 1, "msg": "ok", "data": {"order_no": "HY001"}, "time": 1756684900},
        )
        result = make_client().upload_payment_proof("HY001", "https://cdn.example.test/p.jpg")
        assert result == {"order_no": "HY001"}
        form = _form_of(responses.calls[0].request)
        assert form["order_no"] == ["HY001"]
        assert form["proof_image_url"] == ["https://cdn.example.test/p.jpg"]

    @responses.activate
    def test_confirm_payment_omits_none_proof(self):
        """payment_proof=None：该键完全不上行（连空值都不传）。"""
        responses.post(
            f"{BASE}/merchant/confirmPayment",
            json={"code": 1, "msg": "ok", "data": {"order_no": "HY001"}, "time": 1756684900},
        )
        result = make_client().confirm_payment("HY001")
        assert result == {"order_no": "HY001"}
        form = _form_of(responses.calls[0].request)
        assert "payment_proof" not in form
        assert form["order_no"] == ["HY001"]

    @responses.activate
    def test_confirm_payment_sends_proof_when_given(self):
        responses.post(
            f"{BASE}/merchant/confirmPayment",
            json={"code": 1, "msg": "ok", "data": {"order_no": "HY001"}, "time": 1756684900},
        )
        make_client().confirm_payment("HY001", "https://cdn.example.test/proof.png")
        form = _form_of(responses.calls[0].request)
        assert form["payment_proof"] == ["https://cdn.example.test/proof.png"]
