"""命令行：不打开网页也能把闭环跑完。CI 里用的就是这几个子命令。

    python -m atp run --all --triage
    python -m atp lint
    python -m atp triage
    python -m atp draft "登录后加入购物车并结算" --write
    python -m atp doctor --locator "page.locator('#app > div:nth-child(3) > button')" --url ...
    python -m atp serve
"""
from __future__ import annotations

import argparse
import sys
import unicodedata
from pathlib import Path

from atp import __version__, authoring, lint, locator_doctor, registry, store
from atp.config import settings
from atp.runner import RunOptions, run
from atp.triage import distribution, triage_run

STATUS_ICON = {"passed": "✓", "failed": "✗", "skipped": "-", "error": "!", "unknown": "?"}


def _width(text: str) -> int:
    """中文占两列，表格才不会歪。"""
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def _pad(text: str, width: int) -> str:
    return text + " " * max(0, width - _width(text))


def _table(headers: list[str], rows: list[list[str]]) -> str:
    widths = [_width(h) for h in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], _width(cell))
    lines = ["  ".join(_pad(h, widths[i]) for i, h in enumerate(headers))]
    lines.append("  ".join("-" * widths[i] for i in range(len(headers))))
    for row in rows:
        lines.append("  ".join(_pad(cell, widths[i]) for i, cell in enumerate(row)))
    return "\n".join(lines)


# ---------------- 子命令 ----------------
def cmd_run(args: argparse.Namespace) -> int:
    selector = "" if args.all else args.selector
    if args.marker:
        selector = f"-m '{args.marker}'"
    # 指定了具体用例就别再套 -m 过滤，否则会「1 deselected」跑了个寂寞
    if args.node_ids and not args.marker and not args.all:
        selector = ""

    options = RunOptions(selector=selector, node_ids=args.node_ids, trigger="cli", headed=args.headed)
    record = run(options)

    print()
    print(f"运行 #{record.id} · {record.status} · {record.duration}s")
    print(
        f"用例 {record.total}｜通过 {record.passed}｜失败 {record.failed}｜跳过 {record.skipped}"
        f"｜通过率 {record.pass_rate * 100:.0f}%"
    )
    if record.report_path:
        print(f"报告文件：{record.report_path}")
    if record.stdout_tail and record.status == "error":
        print("\n[原始输出尾部]")
        print(record.stdout_tail[-2000:])

    if record.failed and args.triage:
        results = triage_run(record, refine_with_llm=args.llm)
        print("\n失败归因")
        print(
            _table(
                ["用例", "归因", "置信度", "原因", "建议"],
                [
                    [
                        result.title or result.nodeid.split("::")[-1],
                        result.failure_class.value,
                        f"{result.confidence:.2f}",
                        result.reason,
                        result.suggestion,
                    ]
                    for result in results
                ],
            )
        )

    if args.json:
        print()
        print(record.model_dump_json(indent=2))

    return 1 if record.failed or record.status == "error" else 0


def cmd_lint(args: argparse.Namespace) -> int:
    violations = lint.check(
        tests_dir=Path(args.tests_dir) if args.tests_dir else None,
        pages_dir=Path(args.pages_dir) if args.pages_dir else None,
    )
    if not violations:
        print("✓ PO 纪律检查通过：tests/ 里没有定位，pages/ 里没有断言。")
        return 0

    print(f"✗ 发现 {len(violations)} 处违规：")
    print()
    print(
        _table(
            ["规则", "位置", "代码", "怎么改"],
            [
                [v.rule, f"{v.file}:{v.line}", v.snippet, v.hint]
                for v in violations
            ],
        )
    )
    return 1


def cmd_triage(args: argparse.Namespace) -> int:
    record = store.get_run(args.run_id) if args.run_id else store.latest_run()
    if not record:
        print("还没有任何运行记录，先跑一次：python -m atp run --all")
        return 1

    results = triage_run(record, refine_with_llm=args.llm)
    print(f"运行 #{record.id}（{record.created_at}，{record.status}）")
    if not results:
        print("✓ 这次没有失败用例，不需要归因。")
        return 0

    print("分布：" + "，".join(f"{k} {v}" for k, v in distribution(results).items()))
    print()
    print(
        _table(
            ["用例", "归因", "置信度", "原因", "建议"],
            [
                [r.title or r.nodeid.split("::")[-1], r.failure_class.value, f"{r.confidence:.2f}", r.reason, r.suggestion]
                for r in results
            ],
        )
    )
    return 0


def cmd_draft(args: argparse.Namespace) -> int:
    result = authoring.draft_case(args.requirement, write=args.write)
    print(f"provider = {result.provider}｜valid = {result.valid}")
    for note in result.notes:
        print(f"  · {note}")
    if result.errors:
        for error in result.errors:
            print(f"  ✗ {error}")
    print()
    for name, source in result.files.items():
        print(f"--- {name} ---")
        print(source)
    if result.written:
        print("已写入：" + "，".join(result.written))
    store.save_draft(result)
    return 0 if result.valid else 1


def cmd_cases(args: argparse.Namespace) -> int:
    cases = registry.scan()
    if not cases:
        print("tests/ 下没扫到用例。")
        return 1

    latest = store.latest_run()
    outcomes: dict[str, str] = {}
    if latest:
        for case in latest.cases:
            outcomes[case.nodeid.split("[")[0]] = case.outcome

    print(f"共 {len(cases)} 条用例（真源是 tests/，平台只做索引）")
    print()
    rows = [
        [
            STATUS_ICON.get(outcomes.get(case.nodeid, "unknown"), "?"),
            case.nodeid.split("::")[-1],
            case.title[:28],
            ",".join(case.markers) or "-",
            "浏览器" if case.has_browser else "-",
        ]
        for case in cases
    ]
    print(_table(["态", "函数", "标题", "标记", "类型"], rows))
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    html = Path(args.html).read_text(encoding="utf-8") if args.html else None
    if not html:
        if not args.url:
            print("需要 --html 快照文件或 --url 页面地址")
            return 2
        html = locator_doctor.fetch_snapshot(args.url)

    candidates = locator_doctor.propose(args.locator, html)
    print(f"旧定位：{args.locator}")
    print()
    if not candidates:
        print("页面里没找到可交互元素，快照可能是空壳（检查是否需要登录）。")
        return 1

    print(_table(["分数", "候选定位", "元素"], [[f"{c.score:.2f}", c.locator, c.kind] for c in candidates]))
    print()
    print("提醒：分数只反映「旧选择器里有没有同名文本」，最终抽三条人工验一遍。")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from atp.api import app

    host = args.host or settings.host
    port = args.port or settings.port
    print(f"平台已启动：http://{host}:{port}")
    print("按 Ctrl+C 退出。")
    uvicorn.run(app, host=host, port=port, log_level="warning")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    record = store.get_run(args.run_id) if args.run_id else store.latest_run()
    if not record or not record.report_path:
        print("还没有报告，先跑一次：python -m atp run --all")
        return 1
    print(record.report_path)
    return 0


# ---------------- 入口 ----------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="atp", description=f"AI 测试平台 v{__version__}")
    parser.add_argument("--version", action="version", version=f"atp {__version__}")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="执行用例并出报告")
    p_run.add_argument("node_ids", nargs="*", help="只跑指定用例（nodeid）")
    p_run.add_argument("--selector", default="-m 'not draft'", help="pytest 选择器")
    p_run.add_argument("--marker", "-m", default=None, help="按标记跑，如 smoke")
    p_run.add_argument("--all", action="store_true", help="全部用例（含 draft）")
    p_run.add_argument("--headed", action="store_true", help="显示浏览器窗口")
    p_run.add_argument("--triage", action="store_true", help="跑完立即归因")
    p_run.add_argument("--llm", action="store_true", help="归因时调用 LLM（需配置 key）")
    p_run.add_argument("--json", action="store_true", help="输出完整 JSON")
    p_run.set_defaults(func=cmd_run)

    p_lint = sub.add_parser("lint", help="检查 PO 分层纪律")
    p_lint.add_argument("--tests-dir", default=None)
    p_lint.add_argument("--pages-dir", default=None)
    p_lint.set_defaults(func=cmd_lint)

    p_triage = sub.add_parser("triage", help="归因最近一次运行")
    p_triage.add_argument("--run-id", type=int, default=None)
    p_triage.add_argument("--llm", action="store_true")
    p_triage.set_defaults(func=cmd_triage)

    p_draft = sub.add_parser("draft", help="一句话生成用例草稿")
    p_draft.add_argument("requirement", help="自然语言需求")
    p_draft.add_argument("--write", action="store_true", help="写入 tests/drafts/")
    p_draft.set_defaults(func=cmd_draft)

    p_cases = sub.add_parser("cases", help="列出用例")
    p_cases.set_defaults(func=cmd_cases)

    p_doctor = sub.add_parser("doctor", help="改版后重建语义定位")
    p_doctor.add_argument("--locator", required=True, help="旧定位")
    p_doctor.add_argument("--html", default=None, help="页面快照文件")
    p_doctor.add_argument("--url", default=None, help="页面地址（会真开浏览器取快照）")
    p_doctor.set_defaults(func=cmd_doctor)

    p_serve = sub.add_parser("serve", help="启动平台服务")
    p_serve.add_argument("--host", default=None)
    p_serve.add_argument("--port", type=int, default=None)
    p_serve.set_defaults(func=cmd_serve)

    p_report = sub.add_parser("report", help="打印最近一次报告路径")
    p_report.add_argument("--run-id", type=int, default=None)
    p_report.set_defaults(func=cmd_report)

    return parser


def _force_utf8_stdout() -> None:
    """Windows 下 stdout 被管道接走时常退回 cp1252，中文与 ✓/✗ 会直接抛 UnicodeEncodeError。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def main(argv: list[str] | None = None) -> int:
    _force_utf8_stdout()
    parser = build_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    store.init_db()
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())