"""用例层公共装置：起环境、给夹具、挂现场。

三条纪律在这里落地：
1. 每条用例独立浏览器上下文（不共用登录态，一条挂了不连带后面全挂）；
2. 失败必留截图 + URL + 控制台日志；
3. 被测环境可切换（ATP_BASE_URL 留空走内置演示站）。
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from pages import InventoryPage, LoginPage
from utils import evidence
from utils.config import settings
from utils.data import VALID_ACCOUNT
from utils.demo_server import demo_server
from utils.logger import get_logger

log = get_logger("conftest")


@pytest.fixture(scope="session")
def app_url() -> str:
    """被测环境地址：真实环境直接用，否则拉起内置演示站。"""
    if settings.has_remote_env:
        log.info("使用外部环境：%s", settings.base_url)
        yield settings.base_url
        return
    # 注意：必须是生成器，否则 with 会在返回前把演示站关掉
    with demo_server() as url:
        yield url


@pytest.fixture
def app(page, app_url, request):
    """带现场采集的页面上下文。

    page 由 pytest-playwright 提供（每条用例一个新 context），
    这里只负责挂监听 + 失败时把现场交出去。
    """
    console_logs: list[str] = []
    page.on("console", lambda msg: console_logs.append(f"[{msg.type}] {msg.text}"))
    page.on("pageerror", lambda err: console_logs.append(f"[pageerror] {err}"))
    page.goto(f"{app_url}/index.html", wait_until="domcontentloaded")

    yield SimpleNamespace(page=page, base_url=app_url, logs=console_logs)

    report = getattr(request.node, "rep_call", None)
    if report is not None and report.failed:
        info = evidence.capture(page, request.node.nodeid, console_logs, app_url)
        log.info("失败现场已保存：%s", info.get("evidence_json", "（截图未生成）"))


@pytest.fixture
def login_page(app) -> LoginPage:
    return LoginPage(app.page, app.base_url).open()


@pytest.fixture
def inventory_page(app) -> InventoryPage:
    """已登录状态：每用例独立登录，不复用 storage_state。"""
    login = LoginPage(app.page, app.base_url).open()
    return login.login_as(VALID_ACCOUNT)


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):  # noqa: ANN001 - pytest 钩子签名固定
    outcome = yield
    report = outcome.get_result()
    setattr(item, f"rep_{report.when}", report)