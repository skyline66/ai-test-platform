"""执行调度：一次运行 = 一个独立目录 + 一份结构化结果 + 一份报告。

三件事在这里被钉死：
1. 每次运行产物隔离（artifacts/runs/<id>/），不会互相覆盖；
2. 环境变量随运行下发给子进程（ATP_ARTIFACTS 重定向，现场归档到本次运行目录）；
3. 结果落库 + 出报告，失败用例自动归因。
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from atp import registry, report, store
from atp.config import ROOT, settings
from atp.models import CaseResult, RunRecord, now_iso
from atp.triage import classify
from utils.evidence import safe_name

# 同一时刻只允许一次运行：并发跑同一套浏览器用例，失败的八成是你自己。
RUN_LOCK = threading.Lock()


@dataclass
class RunOptions:
    selector: str = "-m 'not draft'"
    node_ids: list[str] = field(default_factory=list)
    trigger: str = "manual"
    headed: bool = False


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _title_map() -> dict[str, str]:
    """用例标题从注册表拿（allure.title / docstring），别用 nodeid 硬凑。"""
    mapping: dict[str, str] = {}
    for case in registry.scan():
        mapping[case.nodeid] = case.title
    return mapping


def _stage_duration(entry: dict) -> float:
    total = 0.0
    for stage in ("setup", "call", "teardown"):
        total += float((entry.get(stage) or {}).get("duration") or 0.0)
    return round(total, 3)


def _longrepr(entry: dict) -> str:
    """把三段的报错拼起来：setup 挂（夹具）和 teardown 挂同样要看得到。"""
    chunks: list[str] = []
    for stage in ("setup", "call", "teardown"):
        stage_data = entry.get(stage) or {}
        longrepr = stage_data.get("longrepr")
        if longrepr:
            text = longrepr if isinstance(longrepr, str) else json.dumps(longrepr, ensure_ascii=False)
            chunks.append(f"[{stage}]\n{text}")
    return "\n\n".join(chunks)[:6000]


def _load_evidence(run_dir: Path, nodeid: str) -> tuple[str, str, list[str]]:
    """读取 conftest 保存的现场（截图/URL/控制台）。"""
    path = run_dir / "evidence" / f"{safe_name(nodeid)}.json"
    if not path.exists():
        return "", "", []
    try:
        info = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "", "", []

    shot = ""
    if info.get("screenshot"):
        shot = f"evidence/{info['screenshot']}"
    return shot, info.get("url", ""), list(info.get("console") or [])


def _new_run_dir() -> Path:
    base = settings.runs_dir / _stamp()
    candidate = base
    index = 1
    while candidate.exists():
        index += 1
        candidate = base.with_name(f"{base.name}-{index}")
    candidate.mkdir(parents=True, exist_ok=True)
    return candidate


def run(options: RunOptions | None = None) -> RunRecord:
    options = options or RunOptions()
    settings.ensure_dirs()

    run_dir = _new_run_dir()
    json_path = run_dir / "pytest-report.json"
    allure_dir = run_dir / "allure-results"
    targets = options.node_ids or [settings.tests_dir]

    command = [
        sys.executable,
        "-m",
        "pytest",
        *targets,
        "-p",
        "no:cacheprovider",
        "--json-report",
        f"--json-report-file={json_path}",
        f"--alluredir={allure_dir}",
        "-q",
        "--tb=short",
    ]
    if options.selector:
        command += shlex.split(options.selector)
    if options.headed:
        command.append("--headed")

    env = os.environ.copy()
    env["ATP_ARTIFACTS"] = str(run_dir)          # 现场写到本次运行目录
    env["PYTHONIOENCODING"] = "utf-8"
    if settings.base_url_value:
        env["ATP_BASE_URL"] = settings.base_url_value

    started = datetime.now()
    record = RunRecord(
        created_at=now_iso(),
        trigger=options.trigger,
        selector=options.selector or " ".join(options.node_ids),
        status="running",
    )

    try:
        completed = subprocess.run(
            command,
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=settings.run_timeout,
        )
        exit_code = completed.returncode
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
    except subprocess.TimeoutExpired as exc:
        exit_code = 124
        stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        stderr = f"运行超过 {settings.run_timeout}s 被终止"

    record.exit_code = exit_code
    record.duration = round((datetime.now() - started).total_seconds(), 2)
    record.stdout_tail = (stdout + "\n" + stderr).strip()[-4000:]

    _fill_from_json(record, json_path, run_dir)
    _set_status(record, exit_code)
    # 先落库拿到 id，再出报告 —— 否则报告页上永远是「运行 #0」
    store.save_run(record)
    _render_report(record, run_dir)
    store.update_run(record)
    return record


def _fill_from_json(record: RunRecord, json_path: Path, run_dir: Path) -> None:
    if not json_path.exists():
        record.status = "error"
        return

    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        record.status = "error"
        return

    titles = _title_map()
    cases: list[CaseResult] = []

    for entry in data.get("tests", []):
        nodeid = entry.get("nodeid", "")
        base_nodeid = nodeid.split("[")[0]
        outcome = entry.get("outcome") or "unknown"
        error_text = _longrepr(entry) if outcome in {"failed", "error"} else ""
        shot, url, console = _load_evidence(run_dir, nodeid)

        case = CaseResult(
            nodeid=nodeid,
            title=titles.get(base_nodeid, base_nodeid),
            outcome=outcome,
            duration=_stage_duration(entry),
            error_text=error_text,
            screenshot=shot,
            evidence_url=url,
            console=console,
        )
        if case.failed:
            failure_class, _confidence, reason, _suggestion = classify(error_text, console)
            case.failure_class = failure_class
            case.failure_reason = reason
        cases.append(case)

    record.cases = cases

    summary = data.get("summary") or {}
    record.total = len(cases)
    record.passed = sum(1 for c in cases if c.outcome == "passed")
    record.failed = sum(1 for c in cases if c.failed)
    record.skipped = sum(1 for c in cases if c.outcome == "skipped")
    record.pass_rate = round(record.passed / record.total, 4) if record.total else 0.0

    if summary.get("total") and not record.total:
        # 收集阶段就失败（例如 import 报错），用 summary 兜底
        record.total = int(summary.get("total") or 0)


def _set_status(record: RunRecord, exit_code: int) -> None:
    if not record.cases:
        record.status = "error"
    elif record.failed:
        record.status = "failed"
    else:
        record.status = "passed"

    if exit_code not in (0, 1) and record.status == "passed":
        record.status = "error"


def _render_report(record: RunRecord, run_dir: Path) -> None:
    try:
        report_path = report.render(record, run_dir)
        record.report_path = report_path.relative_to(ROOT).as_posix()
    except Exception as exc:  # noqa: BLE001 - 报告失败不该吞掉测试结果
        record.stdout_tail += f"\n[报告生成失败] {exc}"