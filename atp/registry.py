"""用例管理：静态扫描 tests/，不需要一条一条往库里录。

为什么扫描而不是维护一张表：表一定会和代码漂移。用例的真源永远是用例文件，
平台只做「索引 + 归档」。
"""
from __future__ import annotations

import ast
from pathlib import Path

from atp.config import settings
from atp.models import CaseRef

BROWSER_FIXTURES = {"page", "app", "login_page", "inventory_page", "context", "browser"}


def _const_str(node: ast.AST | None) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return ""


def _decorator_values(func: ast.FunctionDef) -> tuple[str, list[str]]:
    """从装饰器里挖出标题和标记：pytest.mark.x / allure.title("...")。"""
    title, markers = "", []
    for dec in func.decorator_list:
        if not isinstance(dec, ast.Call):
            continue
        target = dec.func
        parts: list[str] = []
        node = target
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        if isinstance(node, ast.Name):
            parts.append(node.id)
        dotted = ".".join(reversed(parts))

        if dotted.startswith("pytest.mark."):
            markers.append(dotted.rsplit(".", 1)[-1])
        elif dotted in {"allure.title", "allure.story", "allure.feature"}:
            value = _const_str(dec.args[0]) if dec.args else ""
            if dotted == "allure.title" and value:
                title = value
    return title, markers


def _module_markers(tree: ast.Module) -> list[str]:
    """抓 `pytestmark = pytest.mark.smoke` 这种模块级标记。"""
    found: list[str] = []
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign):
            names = [t.id for t in stmt.targets if isinstance(t, ast.Name)]
            if "pytestmark" not in names:
                continue
            value = stmt.value
            candidates = value.elts if isinstance(value, ast.List) else [value]
            for item in candidates:
                if isinstance(item, ast.Attribute):
                    found.append(item.attr)
    return found


def scan(root: Path | None = None) -> list[CaseRef]:
    root = root or settings.tests_path
    cases: list[CaseRef] = []
    if not root.exists():
        return cases

    for path in sorted(root.rglob("test_*.py")):
        rel = path.relative_to(settings.tests_path.parent).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue

        module_marks = _module_markers(tree)
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not node.name.startswith("test_"):
                continue

            decorator_title, decorator_marks = _decorator_values(node)
            docstring = ast.get_docstring(node) or ""
            # 标题优先级：allure.title > docstring 首行 > 函数名
            if decorator_title:
                title = decorator_title
            elif docstring:
                title = docstring.splitlines()[0].strip()
            else:
                title = node.name
            fixtures = [a.arg for a in node.args.args if a.arg not in {"self"}]
            markers = sorted(set(module_marks) | set(decorator_marks))

            cases.append(
                CaseRef(
                    nodeid=f"{rel}::{node.name}",
                    title=title,
                    file=rel,
                    line=node.lineno,
                    markers=markers,
                    fixtures=fixtures,
                    has_browser=bool(set(fixtures) & BROWSER_FIXTURES),
                )
            )
    return cases


def by_file(cases: list[CaseRef]) -> dict[str, list[CaseRef]]:
    grouped: dict[str, list[CaseRef]] = {}
    for case in cases:
        grouped.setdefault(case.file, []).append(case)
    return grouped