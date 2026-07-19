"""订单查询接口响应模型。"""

from pydantic import BaseModel


class OrderListItem(BaseModel):
    id: int
    product_name: str
    quantity: int
    total_price: float
    status: str


class OrderListResponse(BaseModel):
    data: list[OrderListItem]
    total: int
    page: int
    page_size: int
