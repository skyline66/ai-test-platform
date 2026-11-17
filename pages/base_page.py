"""PO 基类：只提供「怎么走、怎么定位」的公共能力。

这一层不出现任何断言、不出现任何业务期望值 —— 判断永远留在 tests/。
"""
from __future__ import annotations

from playwright.sync_api import Page

from utils.config import settings


class BasePage:
    path: str = "/"

    def __init__(self, page: Page, base_url: str = "") -> None:
        self.page = page
        self.base_url = (base_url or settings.base_url).rstrip("/")

    # ---- 导航 ----
    def goto(self, path: str | None = None) -> "BasePage":
        url = f"{self.base_url}{path or self.path}"
        self.page.goto(url, wait_until="domcontentloaded")
        return self

    @property
    def url(self) -> str:
        return self.page.url

    def page_title(self) -> str:
        return self.page.title()

    # ---- 常用动作（语义定位，不用 nth-child / xpath）----
    def click_text(self, text: str) -> None:
        self.page.get_by_role("button", name=text).click()

    def fill_label(self, label: str, value: str) -> None:
        self.page.get_by_label(label).fill(value)