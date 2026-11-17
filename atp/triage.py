"""结果分析：把「红了」翻译成「为什么红、今晚该谁加班」。

顺序很关键，因为同一条报错里经常同时出现「断言」和「等待超时」：
expect(...).to_be_visible() 失败时既有 Expected/Received，也有 waiting for locator。
所以规则必须显式排序，并且每条规则都要能说清「为什么是这一类」。

LLM 只在规则置信度不高时补充，且只改「措辞」，不改「结论来源」字段。
"""
from __future__ import annotations

import re

from atp.models import CaseResult, FailureClass, RunRecord, TriageResult

# (分类, 置信度, 正则, 判定理由, 建议)
RULES: list[tuple[FailureClass, float, str, str, str]] = [
    (
        FailureClass.SELECTOR_NOT_FOUND,
        0.95,
        r"strict mode violation",
        "定位命中了多个元素（strict mode 拒绝执行）",
        "把定位收紧：加 exact=True、或用 has_text / 父级过滤缩到唯一元素。",
    ),
    (
        FailureClass.SELECTOR_NOT_FOUND,
        0.92,
        r"element\(s\) not found|resolved to 0 elements|No element matching",
        "元素根本没出现，定位或页面结构已变",
        "用 `python -m atp doctor` 拿新快照重建语义定位；不要用 sleep 兜。",
    ),
    (
        FailureClass.ENV_MISMATCH,
        0.9,
        r"Executable doesn't exist|playwright install|Host system is missing dependencies",
        "环境缺浏览器或缺系统依赖（本地能跑、服务器不能跑的典型）",
        "按 Dockerfile 固化镜像：浏览器版本、时区、字体一起锁死。",
    ),
    (
        FailureClass.NETWORK,
        0.88,
        r"net::ERR_|ERR_CONNECTION|ENOTFOUND|ECONNREFUSED",
        "被测服务连不上（服务没起 / 代理不一致 / DNS）",
        "先查服务健康检查与代理配置，再怀疑用例。",
    ),
    (
        FailureClass.ASSERTION,
        0.86,
        r"Received string:|Received: |Expected string:|Expected: ",
        "元素在，但内容/数量与期望不一致",
        "先确认期望值是不是过期的（文案或数据变更），再看是不是真 bug。",
    ),
    (
        FailureClass.ASSERTION,
        0.8,
        r"AssertionError|^\s*E\s+assert",
        "Python 断言不成立",
        "读断言里的实际值：若是数据问题补测试数据，若是产品问题提 issue。",
    ),
    (
        FailureClass.SELECTOR_NOT_FOUND,
        0.78,
        r"waiting for locator",
        "等待定位超时：元素未出现或处于隐藏态",
        "确认页面是否真的加载完；把等待换成断言式等待并检查可见性条件。",
    ),
    (
        FailureClass.FLAKY,
        0.7,
        r"Target page, context or browser has been closed|Execution context was destroyed",
        "浏览器/上下文被提前关闭，常见于并发或复用登录态",
        "检查是否共用登录态、是否有全局 teardown 提前关浏览器。",
    ),
    (
        FailureClass.TIMEOUT,
        0.66,
        r"Timeout\s+\d+ms exceeded",
        "整体超时，没有更具体的失败点",
        "先看是不是环境慢（对比本地耗时），别第一反应就调大超时。",
    ),
    (
        FailureClass.DATA,
        0.6,
        r"KeyError|fixture '.*' not found|No such file or directory",
        "测试数据或夹具缺失",
        "检查 utils/data.py 与数据准备脚本，别在用例里硬编码数据。",
    ),
    (
        FailureClass.AUTH,
        0.55,
        r"\b401\b|\b403\b|unauthorized|登录态失效",
        "鉴权失败（账号被锁 / token 过期 / 权限变更）",
        "确认测试账号状态与 token 有效期，独立账号别共用。",
    ),
]

DEFAULT_SUGGESTION = "报错信息不足：把完整 traceback 与页面快照补齐后再判，别靠猜。"


def classify(error_text: str, console: list[str] | None = None) -> tuple[FailureClass, float, str, str]:
    """按 RULES 顺序取第一条命中；同时看控制台，接口 5xx 往往只在控制台留痕。"""
    haystack = error_text or ""
    console_text = "\n".join(console or [])
    if console_text:
        haystack = f"{haystack}\n{console_text}"

    for failure_class, confidence, pattern, reason, suggestion in RULES:
        if re.search(pattern, haystack, re.IGNORECASE):
            if failure_class is FailureClass.ASSERTION and "5" in console_text and "00" in console_text:
                return (
                    FailureClass.APP_BUG,
                    0.7,
                    f"{reason}；但控制台有 5xx，功能大概率真挂了",
                    "先按产品缺陷复核（接口 5xx），再考虑断言过期。",
                )
            return failure_class, confidence, reason, suggestion

    return FailureClass.UNKNOWN, 0.2, "没有匹配到已知模式", DEFAULT_SUGGESTION


def triage_case(case: CaseResult, *, refine_with_llm: bool = False) -> TriageResult:
    failure_class, confidence, reason, suggestion = classify(case.error_text, case.console)

    result = TriageResult(
        nodeid=case.nodeid,
        title=case.title,
        failure_class=failure_class,
        confidence=confidence,
        reason=reason,
        suggestion=suggestion,
        source="rule",
    )

    if refine_with_llm and confidence < 0.8:
        from atp.llm import LLMUnavailable, get_client

        client = get_client()
        if client.available:
            try:
                refined = client.refine_triage(case.error_text, failure_class.value)
                if refined:
                    result.reason = refined.get("reason", result.reason)
                    result.suggestion = refined.get("suggestion", result.suggestion)
                    result.source = "llm"
            except (LLMUnavailable, ValueError, KeyError):
                pass

    return result


def triage_run(run: RunRecord, *, refine_with_llm: bool = False) -> list[TriageResult]:
    return [triage_case(case, refine_with_llm=refine_with_llm) for case in run.failed_cases]


def distribution(results: list[TriageResult]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in results:
        counts[item.failure_class.value] = counts.get(item.failure_class.value, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))