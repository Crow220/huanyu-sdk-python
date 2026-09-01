"""签名算法实现，逐步对应 huanyu-sdk-common/spec/signature.md。

算法真源：huanyu-backend MerchantAuth::generateSignature，由测试向量锁定。
"""
import hashlib
import json


def php_json(value) -> str:
    """PHP json_encode 兼容序列化：保插入序、无空格分隔、非 ASCII 原样、'/' 转义为 '\\/'。

    U+2028/U+2029 转义为 \\u2028/\\u2029（PHP json_encode 固有行为，即使
    JSON_UNESCAPED_UNICODE；json.dumps 不会输出该形态，末尾替换安全）。
    """
    s = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return (
        s.replace("/", "\\/")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def sign(params: dict, api_secret: str) -> str:
    """按 spec/signature.md 六步计算签名（向量即真理）。"""
    # 1. 移除 signature 字段本身（若存在）
    filtered = {k: v for k, v in params.items() if k != "signature"}
    # 2. 值为数组/对象的参数：JSON 序列化（保插入序、中文原样、/ 与 U+2028/29 转义）
    processed = {
        k: php_json(v) if isinstance(v, (dict, list)) else v
        for k, v in filtered.items()
    }
    # 3. 顶层按键名升序（ASCII 序）；4. 跳过空串与 null
    #    空值判断必须显式比较：真值判断会误伤 0/False（对照 PHP $value !== '' && $value !== null）
    parts = [
        f"{k}={processed[k]}"
        for k in sorted(processed)
        if processed[k] is not None and processed[k] != ""
    ]
    # 5. 追加 api_secret；6. 取 MD5 并转大写
    raw = "&".join(parts) + f"&api_secret={api_secret}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest().upper()
