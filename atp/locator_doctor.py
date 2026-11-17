"""定位医生：改版之后，把「逐条手改二十个选择器」变成「一次批量重建」。

输入一份页面快照（HTML），输出语义定位候选：get_by_role / get_by_label /
get_by_text / get_by_placeholder。全部离线可跑，不依赖模型。

边界（文章原话）：AI 写得出「能跑的定位」，写不出「稳的定位」。
所以这里只输出候选 + 打分，最终抽三条人工验一遍。
"""
from __future__ import annotations

from html.parser import HTMLParser

from atp.models import LocatorCandidate

INTERACTIVE = {"button", "a", "input", "select", "textarea", "summary"}
TEXT_TAGS = {"button", "a", "summary", "label", "option", "h1", "h2", "h3", "td", "li", "span"}


class _SnapshotParser(HTMLParser):
    """收集可交互元素 + 可读文本 + label 关联。够用就好，不做完整 a11y 树。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.elements: list[dict[str, str]] = []
        self.labels: dict[str, str] = {}
        self._stack: list[dict[str, object]] = []
        self._pending_label_for: str | None = None
        self._label_buffer: list[str] | None = None
        self._label_members: list[int] = []

    # ---- 标签 ----
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {k: (v or "") for k, v in attrs}

        if tag == "label":
            self._label_buffer = []
            self._label_members = []
            self._pending_label_for = attr.get("for") or None
            self._stack.append({"tag": tag, "attr": attr})
            return

        if tag in INTERACTIVE or tag in TEXT_TAGS:
            node = {"tag": tag, "attr": attr, "text": []}
            self._stack.append(node)
            if tag in INTERACTIVE:
                self.elements.append({"tag": tag, **attr, "__id__": str(len(self.elements))})
                node["__ref__"] = str(len(self.elements) - 1)
                if self._label_buffer is not None:  # 隐式关联：<label>文本<input></label>
                    self._label_members.append(len(self.elements) - 1)
            return

        self._stack.append({"tag": tag, "attr": attr, "text": []})

    def handle_data(self, data: str) -> None:
        if self._label_buffer is not None:
            self._label_buffer.append(data)
        for node in reversed(self._stack):
            if node.get("tag") == "label":
                continue  # label 文本单独走缓冲，别重复计入
            if node.get("tag") in INTERACTIVE or node.get("tag") in TEXT_TAGS:
                text = node.get("text")
                if isinstance(text, list):
                    text.append(data)
                break

    def handle_endtag(self, tag: str) -> None:
        if tag == "label":
            self._flush_label()
            if self._stack:
                self._stack.pop()
            return

        for index in range(len(self._stack) - 1, -1, -1):
            node = self._stack[index]
            if node.get("tag") != tag:
                continue
            self._flush_node(node)
            del self._stack[index:]
            break

    # ---- 收尾 ----
    def _flush_label(self) -> None:
        if not self._label_buffer:
            self._label_buffer = None
            self._label_members = []
            return
        text = " ".join("".join(self._label_buffer).split())
        target = self._pending_label_for
        if text:
            if target:
                self.labels.setdefault(target, text)
            else:
                for index in self._label_members:  # 隐式关联（label 包着 input）
                    if 0 <= index < len(self.elements):
                        self.elements[index].setdefault("__label__", text)
        self._label_buffer = None
        self._label_members = []

    def _flush_node(self, node: dict[str, object]) -> None:
        ref = node.get("__ref__")
        if ref is None:
            return
        try:
            element = self.elements[int(str(ref))]
        except (IndexError, ValueError):
            return
        text = "".join(node.get("text") or []).strip()  # type: ignore[arg-type]
        if text:
            element["__text__"] = " ".join(text.split())


def parse_snapshot(html: str) -> _SnapshotParser:
    parser = _SnapshotParser()
    parser.feed(html)
    return parser


def _label_for(parser: _SnapshotParser, element: dict[str, str]) -> str:
    implicit = element.get("__label__", "")
    if implicit:
        return implicit
    element_id = element.get("id", "")
    if element_id and element_id in parser.labels:
        return parser.labels[element_id]
    return ""


def _candidates(parser: _SnapshotParser) -> list[LocatorCandidate]:
    found: list[LocatorCandidate] = []

    for element in parser.elements:
        tag = element.get("tag", "")
        aria = element.get("aria-label", "")
        text = element.get("__text__", "")
        placeholder = element.get("placeholder", "")

        if aria:
            role = element.get("role") or ("link" if tag == "a" else "button" if tag == "button" else "")
            if role:
                found.append(LocatorCandidate(locator=f'get_by_role("{role}", name="{aria}")', kind=role, name=aria))
                continue

        if tag == "button" and text:
            found.append(LocatorCandidate(locator=f'get_by_role("button", name="{text}")', kind="button", name=text))
            continue

        if tag == "a" and text:
            found.append(LocatorCandidate(locator=f'get_by_role("link", name="{text}")', kind="link", name=text))
            continue

        if tag in {"input", "select", "textarea"}:
            label = _label_for(parser, element)
            if label:
                found.append(LocatorCandidate(locator=f'get_by_label("{label}")', kind="input", name=label))
            elif placeholder:
                found.append(
                    LocatorCandidate(locator=f'get_by_placeholder("{placeholder}")', kind="input", name=placeholder)
                )
            elif element.get("value") and element.get("type") in {"submit", "button"}:
                value = element["value"]
                found.append(LocatorCandidate(locator=f'get_by_role("button", name="{value}")', kind="button", name=value))
            continue

        if text and tag in {"h1", "h2", "h3", "li", "td", "span"}:
            found.append(LocatorCandidate(locator=f'get_by_text("{text}")', kind="text", name=text))

    return found


def score_candidates(old_locator: str, candidates: list[LocatorCandidate]) -> list[LocatorCandidate]:
    """打分只看一件事：新定位的可读文本是不是还出现在旧选择器里。

    这是一个粗糙但可解释的启发式：旧定位 `#app > div:nth-child(3) > button`
    不含任何文本，所以所有候选都是低分 —— 这正是「路径式定位不可修」的证据。
    """
    lowered = old_locator.lower()
    for candidate in candidates:
        name = candidate.name.lower()
        score = 0.45
        if name and name in lowered:
            score = 0.95
        elif name and any(part and part in lowered for part in name.split()):
            score = 0.7
        if candidate.kind in {"button", "link"}:
            score += 0.03
        candidate.score = min(round(score, 2), 1.0)
    return sorted(candidates, key=lambda item: -item.score)


def propose(old_locator: str, html: str, limit: int = 8) -> list[LocatorCandidate]:
    parser = parse_snapshot(html)
    candidates = _candidates(parser)
    return score_candidates(old_locator, candidates)[:limit]


def repair(old_locators: list[str], html: str, limit: int = 5) -> dict[str, list[LocatorCandidate]]:
    """批量修定位：一次快照，修 N 条旧定位。"""
    parser = parse_snapshot(html)
    candidates = _candidates(parser)
    return {old: score_candidates(old, list(candidates))[:limit] for old in old_locators}


def fetch_snapshot(url: str, timeout_ms: int = 15000) -> str:
    """拿页面快照。用 playwright 同步 API，和用例层同一套环境。"""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            return page.content()
        finally:
            browser.close()