"""登录模块。本文件里没有一行 locator —— 定位全在 pages/login_page.py。"""
from __future__ import annotations

import allure
import pytest
from playwright.sync_api import expect

from utils.data import TEXT, VALID_ACCOUNT

pytestmark = pytest.mark.smoke


@allure.feature("登录")
@allure.story("正常登录")
@allure.title("手机号 + 验证码登录后进入我的订单")
def test_login_success(login_page):
    inventory = login_page.login_as(VALID_ACCOUNT)

    expect(inventory.heading).to_be_visible()
    expect(inventory.heading).to_have_text(TEXT["orders_title"])


@allure.feature("登录")
@allure.story("验证码错误")
@allure.title("验证码错误时提示「验证码错误」且停留在登录页")
def test_login_wrong_code(login_page):
    login_page.login(VALID_ACCOUNT.phone, "000000")

    expect(login_page.error_message).to_be_visible()
    expect(login_page.error_message).to_have_text(TEXT["err_bad_code"])
    expect(login_page.submit_button).to_be_visible()


@allure.feature("登录")
@allure.story("参数校验")
@allure.title("手机号不足 11 位时给出校验提示")
def test_login_invalid_phone(login_page):
    login_page.fill_phone("138").fill_code(VALID_ACCOUNT.code).submit()

    expect(login_page.error_message).to_be_visible()
    expect(login_page.error_message).to_have_text(TEXT["err_bad_phone"])


@allure.feature("登录")
@allure.story("参数校验")
@allure.title("验证码为空时给出校验提示")
def test_login_empty_code(login_page):
    login_page.fill_phone(VALID_ACCOUNT.phone).submit()

    expect(login_page.error_message).to_be_visible()
    expect(login_page.error_message).to_have_text(TEXT["err_no_code"])