"""顶部导航：横跨所有页面，是「组件比页面更值得抽」的典型。"""
from __future__ import annotations

from playwright.sync_api import Locator, Page

from utils.data import TEXT


class Navbar:
    def __init__(self, page: Page) -> None:
        self.page = page
        self.brand: Locator = page.get_by_test_id("brand")
        # exact=True：页面上的「加入购物车」按钮也含「购物车」三个字，
        # 不收紧会命中 4 个元素 —— 语义定位也要给它一个「边界」。
        self.cart_button: Locator = page.get_by_role("button", name=TEXT["cart"], exact=True)
        self.cart_count: Locator = page.get_by_test_id("cart-count")

    def open_cart(self) -> "Navbar":
        self.cart_button.click()
        return self

    def count(self) -> int:
        return int(self.cart_count.inner_text().strip())