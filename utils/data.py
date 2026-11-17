"""测试数据：账号、商品、期望文案集中在这里。

纪律：用例里不出现魔法字符串。改文案只改这一个文件。
"""
from __future__ import annotations

from dataclasses import dataclass

# 演示环境固定验证码见 demo_app/app.js
VALID_CODE = "123456"


@dataclass(frozen=True)
class Account:
    phone: str
    code: str = VALID_CODE


VALID_ACCOUNT = Account(phone="13800000000")

PRODUCTS = ("橙子礼盒", "橙子果酱", "橙子汽水")
PRODUCT_COUNT = len(PRODUCTS)

TEXT = {
    "cart": "购物车",
    "add_to_cart": "加入购物车",
    "checkout": "结算",
    "close": "关闭",
    "orders_title": "我的订单",
    "cart_empty": "购物车是空的",
    "err_bad_phone": "请输入 11 位手机号",
    "err_no_code": "请输入验证码",
    "err_bad_code": "验证码错误",
}