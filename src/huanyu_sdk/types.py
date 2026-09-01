"""请求参数白名单类型。

白名单逐字对齐 common/spec/api.md；from_dict 只过滤不做校验（必填校验在后端），
并保持插入序——签名时 JSON 化与上行展平的键序都依赖它。
"""
from dataclasses import dataclass, field


@dataclass
class CreateOrderParams:
    """创建订单参数（POST /merchant/createOrder）。"""

    FIELDS = (
        "order_type", "cny_amount", "payment_method", "customer_name",
        "id_card", "mobile", "remark", "merchant_order_no",
    )

    data: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> "CreateOrderParams":
        return cls({k: v for k, v in d.items() if k in cls.FIELDS})

    def to_params(self) -> dict:
        return dict(self.data)


@dataclass
class OrderListFilters:
    """订单列表过滤条件（GET /merchant/orderListApi）。"""

    FIELDS = (
        "page", "limit", "status", "order_type", "start_time", "end_time",
        "order_no", "merchant_order_no", "min_cny_amount", "max_cny_amount",
    )

    data: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> "OrderListFilters":
        return cls({k: v for k, v in d.items() if k in cls.FIELDS})

    def to_params(self) -> dict:
        return dict(self.data)


ORDER_DETAIL_QUERY_FIELDS = ("id", "order_no", "merchant_order_no")


def order_detail_query(d: dict) -> dict:
    """订单详情查询条件（GET /merchant/orderDetailApi，三字段三选一）。"""
    return {k: v for k, v in d.items() if k in ORDER_DETAIL_QUERY_FIELDS}
