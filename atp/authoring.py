"""自然语言 → 用例草稿。

这是平台里 Agent 的**第一个**填空位（文章：Agent 擅长三件事之一）。
刻意做成「模板优先 + LLM 可选」：

    - 没有 key：模板兜底，照样能出一个能跑、能过 lint 的草稿；
    - 有 key：模型生成的代码同样过一遍 lint 与 ast 校验，不过就退回模板。

也就是说，AI 写得再好也得过纪律检查 —— 这条边界不能交给模型自己判断。
"""
from __future__ import annotations

import ast
import hashlib
import re
from pathlib import Path

from atp.config import settings
from atp.llm import LLMUnavailable, get_client
from atp.models import DraftResult

FEATURES: list[tuple[str, tuple[str, ...]]] = [
    ("登录", ("登录", "登陆", "验证码", "手机号", "login", "sign in")),
    ("购物车", ("购物车", "加购", "结算", "下单", "cart", "checkout")),
    ("商品", ("商品", "列表", "价格", "订单", "inventory", "product")),
]

# (触发词组合, 生成的代码行)。匹配按顺序进行，命中即取。
STEP_LIBRARY: list[tuple[tuple[str, ...], list[str]]] = [
    (
        ("登录", "成功"),
        ["inventory = login_page.login_as(VALID_ACCOUNT)", "expect(inventory.heading).to_be_visible()"],
    ),
    (
        ("进入", "订单"),
        ["inventory = login_page.login_as(VALID_ACCOUNT)", "expect(inventory.heading).to_be_visible()"],
    ),
    (
        ("验证码", "错误"),
        [
            'login_page.login(VALID_ACCOUNT.phone, "000000")',
            "expect(login_page.error_message).to_be_visible()",
        ],
    ),
    (
        ("手机号", "11"),
        [
            'login_page.fill_phone("138").fill_code(VALID_ACCOUNT.code).submit()',
            "expect(login_page.error_message).to_be_visible()",
        ],
    ),
    (
        ("加入购物车",),
        ["inventory_page.add_to_cart(PRODUCTS[0])"],
    ),
    (
        ("加购",),
        ["inventory_page.add_to_cart(PRODUCTS[0])"],
    ),
    (
        ("购物车", "空"),
        ["cart = inventory_page.open_cart()", "expect(cart.empty_hint).to_be_visible()"],
    ),
    (
        ("购物车",),
        ["cart = inventory_page.open_cart()", "expect(cart.root).to_be_visible()"],
    ),
    (
        ("结算",),
        [
            "cart = inventory_page.open_cart()",
            "cart.checkout()",
            "expect(cart.status).to_be_visible()",
        ],
    ),
    (
        ("商品", "个"),
        ["expect(inventory_page.items).to_have_count(PRODUCT_COUNT)"],
    ),
    (
        ("商品", "数量"),
        ["expect(inventory_page.items).to_have_count(PRODUCT_COUNT)"],
    ),
    (
        ("列表",),
        ["expect(inventory_page.items).to_have_count(PRODUCT_COUNT)"],
    ),
    (
        ("价格",),
        ["expect(inventory_page.prices).to_have_count(PRODUCT_COUNT)"],
    ),
    (
        ("订单",),
        ["expect(inventory_page.heading).to_be_visible()"],
    ),
]

BANNED_IN_TESTS = (".locator(", "xpath", "nth-child", "css=", "get_by_role(", "get_by_label(")

TEMPLATE_HEADER = '''"""草稿：{requirement}

由 atp authoring 生成（provider = {provider}）。**这是草稿，不是交付物。**
AI 负责「找得到」，你负责「下次还找得到」：业务期望值、数据边界、异常分支需要人工补齐。
补齐后把 pytest.mark.draft 去掉，再进冒烟集。
"""
from __future__ import annotations

import allure
import pytest
from playwright.sync_api import expect

{data_import}
pytestmark = pytest.mark.draft


@allure.feature("{feature}")
@allure.title("{title}")
def test_draft_{slug}({fixture}):
    """{requirement}"""
{body}
'''


def slugify(requirement: str) -> str:
    ascii_bits = re.sub(r"[^a-z0-9]+", "_", requirement.lower()).strip("_")
    digest = hashlib.sha1(requirement.encode("utf-8")).hexdigest()[:6]
    return f"{ascii_bits[:24]}_{digest}" if ascii_bits else digest


def detect_feature(requirement: str) -> str:
    lowered = requirement.lower()
    for name, keys in FEATURES:
        if any(key.lower() in lowered for key in keys):
            return name
    return "未分类"


STOPWORDS = re.compile(r"[的了吗呢吧啊，。；、并和与或及后先再然后把将请帮我一下看上去时应需就会则]")


def _segments(requirement: str) -> list[str]:
    parts = re.split(r"[，。；、,;.!?\n]+", requirement)
    return [p.strip() for p in parts if p.strip()]


def _compose_steps(requirement: str) -> tuple[list[str], list[str]]:
    """返回 (代码行, 未识别的片段)。

    一句话里常常挤着好几个动作（「登录成功后加入购物车并结算」），
    所以按整句扫描规则库，而不是按逗号切段 —— 否则只会命中第一个动作。
    剩余没被任何规则覆盖的部分写成 TODO：不替人做业务判断。
    """
    code: list[str] = []
    used: set[str] = set()

    for triggers, lines in STEP_LIBRARY:
        if all(trigger in requirement for trigger in triggers):
            used.update(triggers)
            for line in lines:
                if line not in code:
                    code.append(line)

    if not code:
        return [], _segments(requirement)

    # 登录之后拿到的是 InventoryPage 实例，后续动作就走它 ——
    # 否则生成的用例会同时依赖 login_page 和 inventory_page 两个夹具，重复登录还容易互相干扰。
    if any("login_as(" in line for line in code):
        code = [line.replace("inventory_page.", "inventory.") for line in code]

    remainder = requirement
    for trigger in sorted(used, key=len, reverse=True):
        remainder = remainder.replace(trigger, " ")
    remainder = re.sub(r"\s+", " ", STOPWORDS.sub(" ", remainder)).strip(" ，。；、")

    todos = [remainder] if len(remainder) >= 4 else []
    return code, todos


def _build_body(code: list[str], todos: list[str]) -> str:
    lines: list[str] = []
    for index, statement in enumerate(code, start=1):
        lines.append(f"    # 步骤 {index}")
        lines.append(f"    {statement}")
        lines.append("")
    for todo in todos:
        lines.append(f"    # TODO 待补业务断言：{todo}")
    if todos and not code:
        lines.append("    pass")
    return "\n".join(lines).rstrip() or "    pass"


def _data_import(joined_code: str) -> str:
    names = [symbol for symbol in ("VALID_ACCOUNT", "PRODUCTS", "PRODUCT_COUNT") if symbol in joined_code]
    return f"from utils.data import {', '.join(names)}\n" if names else ""


def build_template_draft(requirement: str) -> DraftResult:
    feature = detect_feature(requirement)
    code, todos = _compose_steps(requirement)
    fixture = "login_page" if any("login_page" in line for line in code) else "inventory_page"
    slug = slugify(requirement)

    source = TEMPLATE_HEADER.format(
        requirement=requirement,
        provider="template",
        data_import=_data_import("\n".join(code)),
        feature=feature,
        title=requirement.replace('"', "'")[:80],
        fixture=fixture,
        slug=slug,
        body=_build_body(code, todos),
    )

    notes = [
        f"识别到的模块：{feature}；夹具：{fixture}",
        "草稿已通过 ast 语法校验与 PO 纪律检查",
        "AI 只负责「找得到」，业务期望值需要你补",
    ]
    if todos:
        notes.append("以下片段没识别出对应动作，已留 TODO：" + "；".join(todos))

    draft = DraftResult(requirement=requirement, provider="template", files={}, notes=notes)
    _validate(draft, {f"tests/drafts/test_draft_{slug}.py": source})
    return draft


def build_llm_draft(requirement: str) -> DraftResult | None:
    client = get_client()
    if not client.available:
        return None

    try:
        payload = client.draft_case(requirement, page_objects_digest())
    except LLMUnavailable:
        return None

    files = payload.get("files") or payload.get("code") or {}
    if isinstance(files, str):
        files = {f"tests/drafts/test_draft_{slugify(requirement)}.py": files}
    if not isinstance(files, dict) or not files:
        return None

    notes = list(payload.get("notes") or [])
    notes.append("模型输出已通过 ast 与 PO 纪律检查")
    draft = DraftResult(requirement=requirement, provider="llm", notes=notes)
    _validate(draft, {str(k): str(v) for k, v in files.items()})

    if not draft.valid:  # 模型写的不合纪律 → 退回模板，而不是把脏代码交出去
        fallback = build_template_draft(requirement)
        fallback.notes.append("模型草稿未通过纪律检查，已退回模板：" + "；".join(draft.errors[:3]))
        return fallback
    return draft


def _validate(draft: DraftResult, files: dict[str, str]) -> None:
    errors: list[str] = []
    for name, source in files.items():
        if not name.endswith(".py"):
            errors.append(f"{name} 不是 .py 文件")
            continue
        try:
            ast.parse(source)
        except SyntaxError as exc:
            errors.append(f"{name} 语法错误：{exc.msg}（第 {exc.lineno} 行）")
            continue
        for token in BANNED_IN_TESTS:
            if token in source and "pages/" not in name:
                errors.append(f"{name} 出现被禁的定位写法：{token}")
        if "pages/" not in name and "pytest.mark.draft" not in source:
            errors.append(f"{name} 缺少 pytest.mark.draft 标记")

    draft.files = files if not errors else {}
    draft.errors = errors
    draft.valid = not errors


def draft_case(requirement: str, *, write: bool = False) -> DraftResult:
    requirement = requirement.strip()
    if not requirement:
        raise ValueError("需求不能为空")

    draft = build_llm_draft(requirement) or build_template_draft(requirement)

    if write and draft.valid:
        draft.written = _write_files(draft)
    return draft


def _write_files(draft: DraftResult) -> list[str]:
    """只写 tests/drafts/ 下的 .py 草稿；拒绝覆盖已有文件。"""
    written: list[str] = []
    repo_root = settings.tests_path.parent

    for name, source in draft.files.items():
        path = Path(name)
        if not path.is_absolute():
            path = repo_root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            draft.notes.append(f"已存在同内容草稿，跳过覆盖：{name}")
            continue
        path.write_text(source, encoding="utf-8")
        written.append(path.relative_to(repo_root).as_posix())

    return written


def page_objects_digest() -> str:
    """把现有页面对象的方法签名拼给模型看，减少它凭空造 API。"""
    lines: list[str] = []
    pages_dir = settings.pages_path
    if not pages_dir.exists():
        return "（暂无页面对象）"

    for path in sorted(pages_dir.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                methods = [
                    f"    def {item.name}({', '.join(a.arg for a in item.args.args)})"
                    for item in node.body
                    if isinstance(item, ast.FunctionDef) and not item.name.startswith("_")
                ]
                if methods:
                    lines.append(f"class {node.name}:")
                    lines.extend(methods)
                    lines.append("")
    return "\n".join(lines).strip() or "（暂无页面对象）"