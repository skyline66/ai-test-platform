"""购物车弹窗：组件级场景。"""
from __future__ import annotations

import allure
import pytest
from playwright.sync_api import expect

from utils.data import PRODUCTS

pytestmark = pytest.mark.regression


@allure.feature("购物车")
@allure.story("空态")
@allure.title("未加商品时购物车展示空态提示")
def test_cart_empty_state(inventory_page):
    cart = inventory_page.open_cart()

    expect(cart.root).to_be_visible()
    expect(cart.empty_hint).to_be_visible()
    expect(cart.items).to_have_count(0)


@allure.feature("购物车")
@allure.story("清单")
@allure.title("加入两件商品后购物车按加入顺序展示")
def test_cart_shows_added_items(inventory_page):
    inventory_page.add_to_cart(PRODUCTS[0]).add_to_cart(PRODUCTS[1])

    cart = inventory_page.open_cart()

    expect(cart.items).to_have_count(2)
    assert cart.item_names() == [PRODUCTS[0], PRODUCTS[1]]


@allure.feature("购物车")
@allure.story("结算")
@allure.title("结算后提示订单提交成功并清空购物车")
def test_checkout_clears_cart(inventory_page):
    inventory_page.add_to_cart(PRODUCTS[0])
    cart = inventory_page.open_cart()

    cart.checkout()

    expect(cart.status).to_be_visible()
    expect(cart.status).to_have_text(f"已提交订单，共 1 件商品")
    expect(inventory_page.navbar.cart_count).to_have_text("0")


@allure.feature("购物车")
@allure.story("空态")
@allure.title("空购物车点结算给出提示")
def test_checkout_empty_cart_hint(inventory_page):
    cart = inventory_page.open_cart()

    cart.checkout()

    expect(cart.status).to_be_visible()
    expect(cart.status).to_have_text("购物车是空的，无法结算")