"""购物车弹窗：一个跨页面复用的组件，抽成组件比抽成 Page 划算。"""
from __future__ import annotations

from playwright.sync_api import Locator, Page

from utils.data import TEXT


class CartDialog:
    """只回答「怎么点」，不回答「点了算不算对」。"""

    def __init__(self, page: Page) -> None:
        self.page = page
        self.root: Locator = page.get_by_role("dialog", name=TEXT["cart"])
        self.items: Locator = self.root.get_by_role("listitem")
        self.checkout_button: Locator = self.root.get_by_role("button", name=TEXT["checkout"])
        self.close_button: Locator = self.root.get_by_role("button", name=TEXT["close"])
        self.status: Locator = self.root.get_by_role("status")
        self.empty_hint: Locator = self.root.get_by_text(TEXT["cart_empty"])

    def wait_open(self) -> "CartDialog":
        self.root.wait_for(state="visible")
        return self

    def wait_closed(self) -> "CartDialog":
        self.root.wait_for(state="hidden")
        return self

    def checkout(self) -> "CartDialog":
        self.checkout_button.click()
        return self

    def close(self) -> "CartDialog":
        self.close_button.click()
        return self

    def item_names(self) -> list[str]:
        return [name.strip() for name in self.items.all_inner_texts()]