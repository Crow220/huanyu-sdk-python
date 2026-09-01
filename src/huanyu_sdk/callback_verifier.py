"""商户回调验签。

入参为回调 POST（application/x-www-form-urlencoded）body 解析出的键值对（含 signature）。
验签通过后商户应输出含 "success" 的 HTTP 200 响应，否则平台按 5/30/120/600s 重试共 5 次。
"""
import hmac

from .signature import sign


class CallbackVerifier:
    def __init__(self, api_secret: str):
        self.api_secret = api_secret

    def verify(self, payload: dict) -> bool:
        """重算签名与回调携带的 signature 恒时比较；缺/空 signature 直接拒绝。"""
        signature = payload.get("signature")
        if not signature:
            return False
        expected = sign(payload, self.api_secret)
        # UTF-8 字节上的恒时比较，避免逐字节短路造成的时序侧信道
        return hmac.compare_digest(
            expected.encode("utf-8"), str(signature).encode("utf-8")
        )
