"""PO 层汇总导出。

纪律：locator / # / xpath 只准出现在本目录。tests/ 里 grep 到任何一处，
`python -m atp lint` 就会报红。
"""
from pages.base_page import BasePage
from pages.inventory_page import InventoryPage
from pages.login_page import LoginPage

__all__ = ["BasePage", "LoginPage", "InventoryPage"]