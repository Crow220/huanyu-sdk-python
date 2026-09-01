"""商户 API 客户端。

merchant_order_no 商户内唯一：同商户重复单号建单返回“商户单号已存在”错误，
超时后可凭同一单号安全重试（返回已存在即代表首单已建成）。

请求管道：注入通用参数 → 在原始嵌套参数上计算签名 → 括号记法展平上行 → 解析响应信封。
签名与展平两条路径互不干扰：Signature.sign 内部对嵌套 dict/list 做 JSON 化，
展平则把它们递归成 payment_method[bank]=ICBC 形态（PHP http_build_query 语义）——
绝不把 dict 直接交给 requests 的 data=（会被 str() 成垃圾串被后端拒）。
"""
import secrets
import time

import requests

from .exceptions import HuanyuApiError
from .signature import sign
from .types import CreateOrderParams, OrderListFilters, order_detail_query

DEFAULT_BASE_URL = "https://api.pisces-pay.cn/addons/huanyu"


def _to_int(value) -> int:
    """对齐 PHP (int) 强转：数值/数字串取整，其余归零而非抛错。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


class Client:
    def __init__(self, api_key, api_secret, base_url=None, timeout=30, session=None):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout
        self.session = session if session is not None else requests.Session()

    def create_order(self, params: dict) -> dict:
        """创建订单（POST /merchant/createOrder），参数经 CreateOrderParams 白名单过滤。"""
        return self._request(
            "POST", "/merchant/createOrder", CreateOrderParams.from_dict(params).to_params()
        )

    def order_list(self, filters: dict = None) -> dict:
        """分页查询订单列表（GET /merchant/orderListApi），条件经 OrderListFilters 白名单过滤。"""
        return self._request(
            "GET", "/merchant/orderListApi", OrderListFilters.from_dict(filters or {}).to_params()
        )

    def order_detail(self, query: dict) -> dict:
        """查询订单详情（GET /merchant/orderDetailApi，id / order_no / merchant_order_no 三选一）。"""
        return self._request("GET", "/merchant/orderDetailApi", order_detail_query(query))

    def upload_payment_proof(self, order_no, proof_image_url) -> dict:
        """上传支付凭证（POST /merchant/uploadPaymentProof）。"""
        return self._request(
            "POST",
            "/merchant/uploadPaymentProof",
            {"order_no": order_no, "proof_image_url": proof_image_url},
        )

    def confirm_payment(self, order_no, payment_proof=None) -> dict:
        """确认付款（POST /merchant/confirmPayment），payment_proof 为 None 时不上行该键。"""
        params = {"order_no": order_no}
        if payment_proof is not None:
            params["payment_proof"] = payment_proof
        return self._request("POST", "/merchant/confirmPayment", params)

    def _request(self, method, path, params: dict) -> dict:
        # 1. 注入通用参数；签名必须在展平前的原始嵌套参数上计算
        #    （服务端验签路径：括号记法重嵌套 → json_encode 重算，两条路径在此汇合）
        params = dict(params)  # 浅拷贝，不改调用方传入的字典
        params["api_key"] = self.api_key
        params["timestamp"] = str(int(time.time()))  # 秒级字符串
        params["nonce"] = secrets.token_hex(8)  # 恰 16 个十六进制字符
        params["signature"] = sign(params, self.api_secret)

        # 2. 发射展平：全量值转 str，requests 的 data=/params= 只收扁平字符串键值
        flat = {}
        for key, value in params.items():
            self._flatten(value, key, flat)

        # 3. GET 走 query、POST 走 form
        if method == "GET":
            response = self.session.request(
                method, self.base_url + path, params=flat, timeout=self.timeout
            )
        else:
            response = self.session.request(
                method, self.base_url + path, data=flat, timeout=self.timeout
            )
        return self._parse_envelope(response)

    @staticmethod
    def _flatten(value, prefix, out: dict) -> None:
        """递归展平为 PHP 表单括号记法：payment_method[bank]=ICBC。

        dict 按插入序递归（键序决定服务端重嵌套后的 JSON 化键序，是验签对齐的关键）；
        list 按下标递归；仅 None 不上行——顶层空串上行后服务端重算同样跳过（等价），
        嵌套空串必须上行以保住 json_encode 键值形态（sign 的跳空值仅作用于顶层标量）。
        """
        if isinstance(value, dict):
            for key, sub in value.items():
                Client._flatten(sub, f"{prefix}[{key}]", out)
        elif isinstance(value, (list, tuple)):
            for index, sub in enumerate(value):
                Client._flatten(sub, f"{prefix}[{index}]", out)
        elif value is None:
            return
        else:
            out[prefix] = str(value)

    @staticmethod
    def _parse_envelope(response) -> dict:
        """响应信封解析：code != 1 抛 HuanyuApiError；非 200 / 非 JSON / 缺 code 抛 RuntimeError。"""
        body_text = response.text
        snippet = body_text[:200]  # 对齐 PHP substr($body, 0, 200)，便于排障且不刷屏
        if response.status_code != 200:
            raise RuntimeError(f"平台响应格式异常: HTTP {response.status_code} {snippet}")
        try:
            body = response.json()
        except ValueError:
            raise RuntimeError(f"平台响应格式异常: {snippet}")
        if not isinstance(body, dict) or "code" not in body:
            raise RuntimeError(f"平台响应格式异常: {snippet}")
        code = _to_int(body["code"])
        if code != 1:
            msg = body.get("msg")
            api_time = body.get("time")  # 缺失或 null 都归 None（对齐 PHP isset）
            raise HuanyuApiError(
                "未知错误" if msg is None else str(msg),
                code,
                None if api_time is None else _to_int(api_time),
            )
        data = body.get("data")
        return {} if data is None else data
