"""商品页（登录后落地页）。断言全部在本文件，页面对象只提供动作。"""
from __future__ import annotations

import allure
import pytest
from playwright.sync_api import expect

from utils.data import PRODUCT_COUNT, PRODUCTS

pytestmark = pytest.mark.smoke


@allure.feature("商品")
@allure.story("列表渲染")
@allure.title("商品列表展示全部商品")
def test_inventory_lists_all_products(inventory_page):
    expect(inventory_page.heading).to_be_visible()
    expect(inventory_page.items).to_have_count(PRODUCT_COUNT)


@allure.feature("商品")
@allure.story("列表渲染")
@allure.title("商品名称与测试数据一致")
def test_inventory_shows_expected_names(inventory_page):
    expect(inventory_page.items).to_have_count(PRODUCT_COUNT)

    assert inventory_page.product_names() == list(PRODUCTS)


@allure.feature("商品")
@allure.story("价格展示")
@allure.title("每个商品都有价格")
def test_inventory_shows_price(inventory_page):
    expect(inventory_page.items).to_have_count(PRODUCT_COUNT)
    expect(inventory_page.prices).to_have_count(PRODUCT_COUNT)

    for price in inventory_page.prices.all_inner_texts():
        assert price.strip().startswith("¥"), f"价格格式异常：{price!r}"


@allure.feature("购物车")
@allure.story("加入购物车")
@allure.title("加入一件商品后导航栏计数变为 1")
def test_add_to_cart_updates_navbar(inventory_page):
    expect(inventory_page.heading).to_be_visible()

    inventory_page.add_to_cart(PRODUCTS[0])

    expect(inventory_page.navbar.cart_count).to_have_text("1")