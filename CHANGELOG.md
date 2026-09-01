# Changelog

## 1.0.0 - 2026-09-01

首个公开发布。

### 功能

- `Client`：封装平台全部对外端点——`create_order`（唯一下单方法，三要素是否必填由商户配置决定）、`order_list`、`order_detail`（dict 风格，id / order_no / merchant_order_no 三选一）、`upload_payment_proof`、`confirm_payment`；自动注入通用参数（api_key / timestamp / nonce / signature），统一解析 `{code, msg, data, time}` 信封，`code != 1` 抛 `HuanyuApiError`。
- `Signature`：与后端 `MerchantAuth` 真源一致的 MD5 签名，由共享规格仓的后端实测向量锁定（9 组用例）。
- `php_json`：PHP `json_encode` 兼容序列化（保插入序、`\/` 与 U+2028/U+2029 转义）。
- 嵌套参数（卖单 `payment_method`）按 PHP 括号记法上行（`payment_method[bank]=…`，dict 插入序即签名序），签名在原始嵌套参数上计算；空串叶子上行、仅 None 跳过。
- `CallbackVerifier`：回调验签（`hmac.compare_digest` 恒时比较）。
- 参数类型白名单过滤：`CreateOrderParams` / `OrderListFilters` / `order_detail_query`。

### 注意

- 金额参数为 `cny_amount`（字符串，如 `"50.00"`）。
- `merchant_order_no` 商户内唯一：重复建单返回"商户单号已存在"，超时可凭同一单号安全重试（示例见 README）。
- 数组参数叶子值用空字符串表示未填，不要传 None（协议限制，见共享 spec）。
- nonce 每次调用自动全新生成（`secrets` 模块），时间窗内一次性有效。

### 环境要求

- Python 3.9+（依赖 requests）；CI 矩阵 3.9–3.13。
