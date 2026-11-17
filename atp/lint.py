"""PO 纪律检查器：把「口头规范」变成「会红的检查」。

文章里那条铁律 —— 「用例文件里 grep 不到 locator、#、xpath。能 grep 出来的规范，
才是能执行的规范。」这个文件就是那条 grep 的可执行版本。

规则：
    TESTS-001  tests/ 里出现原始定位（locator / xpath / css / nth-child）
    TESTS-002  tests/ 里出现 playwright 的原始动作（page.click / page.fill ...）
    PAGES-001  pages/ 里出现断言（页面对象只回答「怎么点」）
    PAGES-002  pages/ 里出现 URL 之外的硬编码期望值（sleep 等）
"""
from __future__ import annotations

import re
from pathlib import Path

from atp.config import settings
from atp.models import Violation

RAW_LOCATOR_PATTERNS = [
    (re.compile(r"\.locator\s*\("), "使用了 .locator()，把定位搬进 pages/"),
    (re.compile(r"(?i)\bxpath\b"), "使用了 xpath，改用 role / label / text"),
    (re.compile(r"(?i)nth-child|nth-of-type"), "使用了层级选择器，改用语义定位"),
    (re.compile(r"[\"']css="), "使用了 css= 选择器，改用语义定位"),
    (re.compile(r"[\"']#[A-Za-z][\w-]*[\"']"), "使用了 id 选择器（#xxx），改用语义定位"),
    (re.compile(r"get_by_(role|label|text|test_id|placeholder)\s*\("), "用例层直接写定位，交给 pages/"),
]

RAW_ACTION_PATTERNS = [
    (re.compile(r"\bpage\.(click|fill|goto|type|hover|check)\s*\("), "用例层直接操作 page，封装成页面对象方法"),
    (re.compile(r"\.(click|fill|goto|type|hover|check)\s*\("), "用例层直接调元素动作，封装成页面对象方法"),
]

ASSERT_PATTERNS = [
    (re.compile(r"^\s*assert\b", re.M), "页面对象不允许写断言"),
    (re.compile(r"\bexpect\s*\("), "页面对象不允许写 expect 断言"),
    (re.compile(r"to_be_visible|to_have_text|to_have_count|to_contain_text"), "页面对象不允许写断言"),
]

HYGIENE_PATTERNS = [
    (re.compile(r"\btime\.sleep\s*\("), "别用 sleep 赌时间，改用断言式等待"),
    (re.compile(r"\bwait_for_timeout\s*\("), "别用固定等待，改用 expect(...) 自带轮询"),
]

SKIP_FILES = {"conftest.py", "__init__.py"}


def _strip_noise(text: str) -> str:
    """去掉注释和文档字符串，避免把说明文字判成违规。"""
    text = re.sub(r'"""(?:.|\n)*?"""', "", text)
    text = re.sub(r"'''(?:.|\n)*?'''", "", text)
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            lines.append("")
        else:
            lines.append(line)
    return "\n".join(lines)


def _scan_file(path: Path, patterns, rule: str) -> list[Violation]:
    raw = path.read_text(encoding="utf-8")
    clean = _strip_noise(raw)
    found: list[Violation] = []
    for number, line in enumerate(clean.splitlines(), start=1):
        for pattern, hint in patterns:
            if pattern.search(line):
                found.append(
                    Violation(
                        rule=rule,
                        file=path.as_posix(),
                        line=number,
                        snippet=line.strip()[:120],
                        hint=hint,
                    )
                )
    return found


def check(tests_dir: Path | None = None, pages_dir: Path | None = None) -> list[Violation]:
    tests_dir = tests_dir or settings.tests_path
    pages_dir = pages_dir or settings.pages_path
    violations: list[Violation] = []

    if tests_dir.exists():
        for path in sorted(tests_dir.rglob("*.py")):
            if path.name in SKIP_FILES:
                continue
            violations += _scan_file(path, RAW_LOCATOR_PATTERNS, "TESTS-001")
            violations += _scan_file(path, RAW_ACTION_PATTERNS, "TESTS-002")

    if pages_dir.exists():
        for path in sorted(pages_dir.rglob("*.py")):
            if path.name in SKIP_FILES:
                continue
            violations += _scan_file(path, ASSERT_PATTERNS, "PAGES-001")
            violations += _scan_file(path, HYGIENE_PATTERNS, "PAGES-002")

    return violations


def summary(violations: list[Violation]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in violations:
        counts[item.rule] = counts.get(item.rule, 0) + 1
    return counts