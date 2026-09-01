# huanyu-sdk-python

PISCES商户平台官方 Python SDK。

## 安装

```
pip install huanyu-sdk
```

## 快速上手

```python
from huanyu_sdk import Client

# base_url 默认指向生产地址，timeout 单位秒；session 可注入自定义 requests.Session
client = Client("你的api_key", "你的api_secret")

# 创建订单（三要素字段是否必填由商户配置决定）
order = client.create_order({
    "order_type": "1",                    # 1=买入 2=卖出
    "cny_amount": "100.00",
    "merchant_order_no": "M20260831001",  # 商户内唯一，重复会被拒绝
})
# order["result_status"] == "pending_identity" 时，引导用户访问 order["identity_url"] 补全身份信息

# 卖出示例：payment_method 必填，用普通 dict 按固定字段顺序书写——
# key 插入序即签名序（Python 3.7+ 的 dict 保插入序），不要从 set 等无序来源构造、也不要对键重排序
sell_order = client.create_order({
    "order_type": "2",
    "cny_amount": "100.00",
    "merchant_order_no": "M20260831002",  # 换一个商户单号：同商户重复单号会被"商户单号已存在"拒绝
    "payment_method": {
        "bank": "中国工商银行",
        "sub_bank": "杭州某某支行",
        "card_number": "6222020200112233445",
        "real_name": "张三",
    },
})

# 查询
orders = client.order_list({"status": "paid,confirmed", "page": 1, "limit": 20})
detail = client.order_detail({"order_no": order["order_no"]})  # id / order_no / merchant_order_no 三选一

# 卖单确认付款 / 上传凭证（payment_proof 不传即不上行该字段）
client.confirm_payment(order["order_no"])
client.upload_payment_proof(order["order_no"], "https://your.cdn/proof.png")
```

## 回调处理

```python
from huanyu_sdk import CallbackVerifier

verifier = CallbackVerifier("你的api_secret")
```

Flask：

```python
@app.post("/callback")
def callback():
    # 平台以 application/x-www-form-urlencoded POST，request.form 即键值对（含 signature）
    if not verifier.verify(request.form):
        abort(403)
    # ...业务处理（回调仅在订单 completed 时推送）
    return "success", 200  # 必须响应 HTTP 200 且含 success，否则平台按 5/30/120/600s 共推送 5 次（首次 + 4 次重试）
```

Django：

```python
@csrf_exempt  # 平台服务器直连回调，无 CSRF cookie
def callback(request):
    if request.method != "POST":
        return HttpResponse(status=405)
    # request.POST 已解析 application/x-www-form-urlencoded 键值对（含 signature）
    if not verifier.verify(request.POST):
        return HttpResponse(status=403)
    # ...业务处理（回调仅在订单 completed 时推送）
    return HttpResponse("success")  # 必须响应 HTTP 200 且含 success，否则平台按 5/30/120/600s 共推送 5 次（首次 + 4 次重试）
```

## 重要注意事项

- **merchant_order_no 商户内唯一**：同一商户重复单号建单返回"商户单号已存在"错误（不同商户间可重复）。网络超时后可用同一单号安全重试——若返回"已存在"，说明首单已建成，请按单号查单确认状态：

```python
from huanyu_sdk import HuanyuApiError

try:
    order = client.create_order(params)
except HuanyuApiError as e:
    if "商户单号已存在" in str(e):  # str(e) 即平台返回的业务消息
        # 首单已建成：按商户单号查单确认状态即可，不要重复下单
        order = client.order_detail({"merchant_order_no": "M20260831001"})
    else:
        raise
```

- **数组参数叶子值用空字符串表示"未填"**：payment_method 的可选字段请 `"sub_bank": ""` 显式传空串，不要传 None（None 不上行，服务端重算的 JSON 键集会变少，导致验签失败）；叶子值无法表达 null 是表单线路的协议限制。
- **nonce 自动生成**：平台要求每个请求的 nonce 在 10 分钟窗口内一次性有效（防重放）。SDK 每次调用都会自动生成全新的 timestamp/nonce/signature，失败后直接再次调用即可，无需（也不要）缓存复用请求参数。
- timestamp 为秒级时间戳，本机时钟偏差超过 ±300 秒会验签失败。

## 要求

- Python 3.9+
