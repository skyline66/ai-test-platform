"""平台自身的单测。

为什么单独一个目录：这套测试不需要浏览器，几秒跑完，适合放进 CI 的第一道闸。
真正的用例在 tests/（需要浏览器），两者不该混在一起。
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from atp import authoring, lint, locator_doctor, registry, store
from atp.models import CaseResult, FailureClass, RunRecord
from atp.triage import classify


# ---------------- 纪律检查 ----------------
def test_repo_passes_lint():
    """当前仓库必须自洽：tests/ 没有定位，pages/ 没有断言。"""
    assert lint.check() == []


def test_lint_catches_raw_locator(tmp_path: Path):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_bad.py").write_text(
        'def test_x(page):\n    page.locator("#app > div:nth-child(3)").click()\n',
        encoding="utf-8",
    )

    violations = lint.check(tests_dir=tests_dir, pages_dir=tmp_path / "pages")
    rules = {v.rule for v in violations}

    assert "TESTS-001" in rules
    assert "TESTS-002" in rules


def test_lint_allows_comments_mentioning_banned_words(tmp_path: Path):
    """注释里提到 xpath 不该判红，否则规范没法写进注释。"""
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_ok.py").write_text(
        'def test_x(login_page):\n    # 这里不要用 xpath，改用 role\n    login_page.open()\n',
        encoding="utf-8",
    )

    assert lint.check(tests_dir=tests_dir, pages_dir=tmp_path / "pages") == []


def test_lint_catches_assertion_in_pages(tmp_path: Path):
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    (pages_dir / "login_page.py").write_text(
        "from playwright.sync_api import expect\n\n\ndef check(page):\n    expect(page.get_by_role('button')).to_be_visible()\n",
        encoding="utf-8",
    )

    violations = lint.check(tests_dir=tmp_path / "tests", pages_dir=pages_dir)
    assert {v.rule for v in violations} == {"PAGES-001"}


# ---------------- 用例管理 ----------------
def test_registry_finds_cases_and_markers():
    cases = registry.scan()
    assert len(cases) >= 8

    by_name = {case.nodeid.split("::")[-1]: case for case in cases}
    assert by_name["test_login_success"].markers == ["smoke"]
    assert by_name["test_cart_empty_state"].markers == ["regression"]
    # 标题来自 allure.title，不是函数名
    assert by_name["test_login_success"].title.startswith("手机号")


# ---------------- 起草 ----------------
def test_template_draft_is_valid_python():
    draft = authoring.draft_case("登录成功后加入购物车并结算")

    assert draft.valid, draft.errors
    assert draft.provider == "template"
    source = next(iter(draft.files.values()))
    ast.parse(source)
    assert "pytest.mark.draft" in source
    assert "add_to_cart" in source
    # 不允许把定位写进用例层
    assert "get_by_role(" not in source


def test_template_draft_marks_unknown_steps_as_todo():
    draft = authoring.draft_case("看一下会员等级页面会不会显示钻石标志")

    assert draft.valid
    source = next(iter(draft.files.values()))
    assert "TODO" in source
    assert any("没识别出对应动作" in note for note in draft.notes)


def test_empty_requirement_rejected():
    with pytest.raises(ValueError):
        authoring.draft_case("   ")


# ---------------- 归因 ----------------
@pytest.mark.parametrize(
    ("error_text", "expected"),
    [
        ('get_by_role("button").click: strict mode violation: resolved to 4 elements', FailureClass.SELECTOR_NOT_FOUND),
        ("Locator expected to be visible\nReceived: <element(s) not found>", FailureClass.SELECTOR_NOT_FOUND),
        ("Expected string: '验证码错误' Received string: '验证码不正确'", FailureClass.ASSERTION),
        ("Executable doesn't exist at .../chrome.exe", FailureClass.ENV_MISMATCH),
        ("net::ERR_CONNECTION_REFUSED at http://127.0.0.1:8000", FailureClass.NETWORK),
        ("AssertionError: assert [] == ['橙子礼盒']", FailureClass.ASSERTION),
    ],
)
def test_triage_classification(error_text: str, expected: FailureClass):
    failure_class, confidence, reason, suggestion = classify(error_text)

    assert failure_class is expected
    assert confidence > 0
    assert reason and suggestion


# ---------------- 定位医生 ----------------
SNAPSHOT = """
<html><body>
  <label for="phone">手机号</label>
  <input id="phone" placeholder="请输入手机号">
  <button>登录</button>
  <a>我的订单</a>
</body></html>
"""


def test_doctor_proposes_semantic_locators():
    candidates = locator_doctor.propose("page.locator('#app > div:nth-child(3) > button')", SNAPSHOT)
    locators = [item.locator for item in candidates]

    assert any('get_by_label("手机号")' in loc for loc in locators)
    assert any('get_by_role("button", name="登录")' in loc for loc in locators)
    # 一个路径式选择器不含任何文本，所有候选都只能是低分 —— 这就是「路径不可修」
    assert all(item.score <= 0.6 for item in candidates)


def test_doctor_boosts_candidates_matching_old_text():
    candidates = locator_doctor.propose('button:has-text("登录")', SNAPSHOT)
    best = candidates[0]

    assert "登录" in best.locator
    assert best.score >= 0.9


# ---------------- 持久化 ----------------
def test_run_record_roundtrip(tmp_path: Path, monkeypatch):
    """用临时库，别把自测数据写进平台的 artifacts/atp.db。"""
    from atp.config import settings

    monkeypatch.setattr(settings, "db_path", str(tmp_path / "atp-test.db"))
    monkeypatch.setattr(settings, "artifacts", str(tmp_path))

    record = RunRecord(trigger="pytest", selector="-m smoke", total=2, passed=1, failed=1, status="failed")
    record.cases = [
        CaseResult(nodeid="tests/test_x.py::test_a[chromium]", title="A", outcome="passed", duration=0.4),
        CaseResult(
            nodeid="tests/test_x.py::test_b[chromium]",
            title="B",
            outcome="failed",
            duration=1.2,
            failure_class=FailureClass.ASSERTION,
            failure_reason="内容不一致",
        ),
    ]

    run_id = store.save_run(record)
    loaded = store.get_run(run_id)

    assert loaded is not None
    assert loaded.id == run_id
    assert loaded.failed == 1
    assert loaded.cases[1].failure_class is FailureClass.ASSERTION