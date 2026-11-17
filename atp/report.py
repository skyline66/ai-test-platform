"""报告：自包含单文件 HTML。

为什么不用现成模板：Allure 解决的是「可追溯」，平台要解决的是「一眼看懂」。
所以这里只做四件事：结论、归因分布、失败现场、原始日志。
截图以 base64 内嵌，报告可以单文件发给别人，不依赖目录结构。
"""
from __future__ import annotations

import base64
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from atp.models import RunRecord
from atp.triage import distribution, triage_run

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _b64(run_dir: Path, relative: str) -> str:
    path = run_dir / relative
    if not path.exists():
        return ""
    try:
        return base64.b64encode(path.read_bytes()).decode("ascii")
    except OSError:
        return ""


def render(record: RunRecord, run_dir: Path) -> Path:
    triage = triage_run(record)
    shots = {case.nodeid: _b64(run_dir, case.screenshot) for case in record.cases if case.screenshot}

    html = _env().get_template("report.html").render(
        run=record,
        triage=triage,
        dist=distribution(triage),
        shots=shots,
        caveat="通过率不是指标：它涨了，可能只是不稳的用例被删了。看误报率和定位耗时。",
    )

    path = run_dir / "report.html"
    path.write_text(html, encoding="utf-8")
    return path


def render_to_string(record: RunRecord, run_dir: Path) -> str:
    triage = triage_run(record)
    shots = {case.nodeid: _b64(run_dir, case.screenshot) for case in record.cases if case.screenshot}
    return _env().get_template("report.html").render(
        run=record,
        triage=triage,
        dist=distribution(triage),
        shots=shots,
        caveat="通过率不是指标：它涨了，可能只是不稳的用例被删了。看误报率和定位耗时。",
    )