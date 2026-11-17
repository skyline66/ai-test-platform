"""商品页对象（登录后的落地页）。

商品列表用 `list / listitem` 语义定位，价格用 data-testid ——
两者的共同点是：前端把 div 嵌套换十层也不会失效。
"""
from __future__ import annotations

from playwright.sync_api import Locator, Page

from pages.base_page import BasePage
from pages.components.cart_dialog import CartDialog
from pages.components.navbar import Navbar
from utils.data import TEXT


class InventoryPage(BasePage):
    path = "/inventory.html"

    def __init__(self, page: Page, base_url: str = "") -> None:
        super().__init__(page, base_url)
        self.heading: Locator = page.get_by_role("heading", name=TEXT["orders_title"])
        self.product_list: Locator = page.get_by_role("list", name="商品列表")
        self.items: Locator = self.product_list.get_by_role("listitem")
        self.prices: Locator = page.get_by_test_id("price")
        self.navbar = Navbar(page)
        self.cart = CartDialog(page)

    def open(self) -> "InventoryPage":
        self.goto(self.path)
        return self

    def item(self, name: str) -> Locator:
        return self.items.filter(has_text=name)

    def add_to_cart(self, name: str) -> "InventoryPage":
        self.item(name).get_by_role("button", name=TEXT["add_to_cart"]).click()
        return self

    def open_cart(self) -> CartDialog:
        self.navbar.open_cart()
        return self.cart.wait_open()

    def product_names(self) -> list[str]:
        return [self.item_name(i) for i in range(self.items.count())]

    def item_name(self, index: int) -> str:
        """商品名在 li 内的 .name 上；索引由调用方给，本方法只负责读。"""
        return self.items.nth(index).locator(".name").inner_text().strip()