"""登录页对象。

允许出现的：定位、动作。
不允许出现的：assert / expect / 业务期望值（「登录成功应该看到我的订单」这句话属于 tests/）。
"""
from __future__ import annotations

from playwright.sync_api import Locator, Page

from pages.base_page import BasePage
from pages.inventory_page import InventoryPage
from utils.data import TEXT


class LoginPage(BasePage):
    path = "/index.html"

    def __init__(self, page: Page, base_url: str = "") -> None:
        super().__init__(page, base_url)
        # 语义定位：绑的是「标签上写着什么」，不是「它在第几层 div 里」
        self.phone_input: Locator = page.get_by_label("手机号")
        self.code_input: Locator = page.get_by_label("验证码")
        self.submit_button: Locator = page.get_by_role("button", name="登录")
        self.error_message: Locator = page.get_by_role("alert")
        self.heading: Locator = page.get_by_role("heading", name="登录")

    def open(self) -> "LoginPage":
        self.goto(self.path)
        return self

    def fill_phone(self, phone: str) -> "LoginPage":
        self.phone_input.fill(phone)
        return self

    def fill_code(self, code: str) -> "LoginPage":
        self.code_input.fill(code)
        return self

    def submit(self) -> None:
        self.submit_button.click()

    def login(self, phone: str, code: str) -> InventoryPage:
        """完整走一遍登录动作，返回登录后的页面对象。"""
        self.fill_phone(phone).fill_code(code).submit()
        return InventoryPage(self.page, self.base_url)

    def login_as(self, account) -> InventoryPage:
        return self.login(account.phone, account.code)