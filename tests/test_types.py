"""请求参数白名单类型测试：白名单过滤、插入序保持、嵌套 dict 透传。"""
from huanyu_sdk.types import (
    CreateOrderParams,
    OrderListFilters,
    order_detail_query,
)

CREATE_ORDER_ALL_FIELDS = [
    "order_type", "cny_amount", "payment_method", "customer_name",
    "id_card", "mobile", "remark", "merchant_order_no",
]


class TestCreateOrderParams:
    def test_from_dict_filters_to_whitelist(self):
        # api_key/signature 等通用参数与任意未知键不得混入业务参数
        params = CreateOrderParams.from_dict({
            **{k: "v" for k in CREATE_ORDER_ALL_FIELDS},
            "api_key": "hack", "signature": "hack", "extra": "x",
        })
        assert list(params.to_params()) == CREATE_ORDER_ALL_FIELDS

    def test_from_dict_preserves_insertion_order(self):
        # 插入序决定签名时 JSON 化的键序，必须原样保持（不做排序/重排）
        params = CreateOrderParams.from_dict({
            "merchant_order_no": "M001",
            "payment_method": {"sub_bank": "杭州分行", "bank": "工商银行"},
            "order_type": 1,
        })
        assert list(params.to_params()) == ["merchant_order_no", "payment_method", "order_type"]

    def test_nested_payment_method_passthrough(self):
        # 嵌套 dict 原样透传（内部插入序同样保持），交由签名/展平阶段处理
        payment_method = {"real_name": "张三", "card_number": "6222020000000000000"}
        params = CreateOrderParams.from_dict({"payment_method": payment_method})
        assert params.to_params()["payment_method"] == payment_method

    def test_to_params_returns_copy(self):
        # 返回副本，调用方改返回值不污染参数对象（对齐 PHP 数组值拷贝语义）
        params = CreateOrderParams.from_dict({"order_type": 1})
        params.to_params()["order_type"] = 2
        assert params.to_params()["order_type"] == 1

    def test_from_dict_empty(self):
        assert CreateOrderParams.from_dict({}).to_params() == {}


class TestOrderListFilters:
    def test_whitelist_keeps_all_ten_fields(self):
        filters = OrderListFilters.from_dict({
            "page": 2, "limit": 50, "status": "pending,paid", "order_type": 1,
            "start_time": "2026-08-01", "end_time": "2026-08-31",
            "order_no": "HY001", "merchant_order_no": "M001",
            "min_cny_amount": "100", "max_cny_amount": "500",
        })
        assert list(filters.to_params()) == [
            "page", "limit", "status", "order_type", "start_time", "end_time",
            "order_no", "merchant_order_no", "min_cny_amount", "max_cny_amount",
        ]

    def test_whitelist_drops_unknown_keys(self):
        filters = OrderListFilters.from_dict({"page": 1, "page_size": 999, "keyword": "x"})
        assert filters.to_params() == {"page": 1}


class TestOrderDetailQuery:
    def test_whitelist_keeps_three_keys(self):
        assert order_detail_query({"id": 5, "order_no": "HY001", "merchant_order_no": "M001", "foo": "x"}) == {
            "id": 5, "order_no": "HY001", "merchant_order_no": "M001",
        }

    def test_empty_query(self):
        assert order_detail_query({}) == {}
