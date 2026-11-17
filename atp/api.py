"""平台 HTTP 层：把内核能力暴露成一组可点、可写的接口。

接口清单（也是平台的四个抽屉）：
    环境与数据  GET  /api/env
    用例管理    GET  /api/cases      POST /api/cases/draft
    执行调度    POST /api/runs       GET  /api/schedule  POST /api/schedule
    结果分析    GET  /api/runs       GET  /api/runs/{id}  GET  /api/runs/{id}/report
"""
from __future__ import annotations

import importlib.metadata as metadata
import os
import platform
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from atp import __version__, authoring, lint, locator_doctor, registry, store
from atp.config import ROOT, settings
from atp.models import SystemInfo
from atp.runner import RUN_LOCK, RunOptions, run
from atp.scheduler import scheduler
from atp.triage import distribution, triage_run

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ANN201 - FastAPI 签名固定
    store.init_db()
    if scheduler.status()["enabled"]:
        scheduler.start()
    yield
    scheduler.stop()


app = FastAPI(title="AI 测试平台", version=__version__, lifespan=lifespan)


# ---------------- 请求模型 ----------------
class DraftRequest(BaseModel):
    requirement: str = Field(min_length=2, description="一句自然语言需求")
    write: bool = Field(default=False, description="是否写入 tests/drafts/")


class RunRequest(BaseModel):
    selector: str = Field(default="-m 'not draft'", description="pytest 选择器，如 -m smoke")
    node_ids: list[str] = Field(default_factory=list, description="只跑指定用例")
    trigger: str = "api"


class ScheduleRequest(BaseModel):
    enabled: bool | None = None
    interval: int | None = Field(default=None, ge=60)
    selector: str | None = None


class DoctorRequest(BaseModel):
    locator: str
    html: str | None = None
    url: str | None = None


class LintRequest(BaseModel):
    tests_dir: str | None = None
    pages_dir: str | None = None


# ---------------- 环境与数据 ----------------
def _browsers_dir() -> Path | None:
    configured = os.getenv("PLAYWRIGHT_BROWSERS_PATH")
    if configured and configured != "0":
        return Path(configured)
    home = Path.home()
    for candidate in (
        home / "AppData" / "Local" / "ms-playwright",
        home / ".cache" / "ms-playwright",
        home / "Library" / "Caches" / "ms-playwright",
    ):
        if candidate.exists():
            return candidate
    return None


def _chromium_revision() -> str:
    """从 playwright 自带的 browsers.json 读修订号。

    不能靠「列目录取最后一个」——本机可能装着好几个 revision，
    真正被用到的那个由 playwright 版本决定，猜错了环境面板就是在骗人。
    """
    try:
        import playwright

        manifest = Path(playwright.__file__).parent / "driver" / "package" / "browsers.json"
        entries = __import__("json").loads(manifest.read_text(encoding="utf-8"))["browsers"]
    except (ImportError, OSError, KeyError, ValueError):
        return ""

    for entry in entries:
        if entry.get("name") == "chromium":
            return str(entry.get("revision", ""))
    return ""


def collect_system_info() -> SystemInfo:
    try:
        playwright_version = metadata.version("playwright")
    except metadata.PackageNotFoundError:
        playwright_version = "未安装"

    revision = _chromium_revision()
    browsers = _browsers_dir()
    if not revision:
        chromium = "未知"
    elif browsers and (browsers / f"chromium-{revision}").is_dir():
        chromium = f"chromium-{revision}"
    else:
        chromium = f"chromium-{revision}（未下载）"

    import datetime

    now = datetime.datetime.now().astimezone()
    offset = now.strftime("%z")
    offset_label = f"UTC{offset[:3]}:{offset[3:]}" if offset else "UTC"

    # Windows 上 tzname() 依赖 C 运行时的代码页，中文时区名常常直接变成 "??????"，
    # 所以以偏移量为准，名字只在「认得出来」时才带上。
    tz_name = (os.getenv("TZ") or now.tzname() or "").strip()
    if not tz_name or "?" in tz_name:
        tz_name = ""
    timezone_label = f"{tz_name} ({offset_label})" if tz_name else offset_label

    return SystemInfo(
        python=platform.python_version(),
        playwright=playwright_version,
        browser=chromium,
        timezone=timezone_label,
        platform=f"{platform.system()} {platform.release()}",
        base_url=settings.base_url_value or "（内置 demo_app）",
        demo_mode=not settings.base_url_value,
        llm_enabled=settings.llm_ready,
        llm_model=settings.llm_model if settings.llm_ready else "",
        artifacts=str(settings.artifacts_dir),
        extra={"python_executable": sys.executable, "root": str(ROOT)},
    )


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "version": __version__}


@app.get("/api/env", response_model=SystemInfo)
def env() -> SystemInfo:
    return collect_system_info()


# ---------------- 用例管理 ----------------
@app.get("/api/cases")
def list_cases() -> dict[str, Any]:
    cases = registry.scan()
    recent = store.list_runs(limit=10)

    # 取「最近一次包含这条用例的运行」的结论。
    # 只看最后一次运行会让「只跑了一条用例」之后全表变 unknown。
    outcome_map: dict[str, str] = {}
    for record in recent:
        for case in record.cases:
            outcome_map.setdefault(case.nodeid.split("[")[0], case.outcome)

    return {
        "total": len(cases),
        "last_run_id": recent[0].id if recent else None,
        "cases": [
            {**case.model_dump(), "last_outcome": outcome_map.get(case.nodeid, "unknown")}
            for case in cases
        ],
    }


@app.post("/api/cases/draft")
def draft_case(payload: DraftRequest) -> dict[str, Any]:
    try:
        result = authoring.draft_case(payload.requirement, write=payload.write)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    draft_id = store.save_draft(result)
    return {"draft_id": draft_id, **result.model_dump()}


@app.get("/api/drafts")
def drafts(limit: int = 20) -> dict[str, Any]:
    return {"drafts": store.list_drafts(limit=limit)}


# ---------------- 执行调度 ----------------
@app.post("/api/runs")
def trigger_run(payload: RunRequest) -> dict[str, Any]:
    if not RUN_LOCK.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="已有运行在进行中，等它跑完")
    try:
        record = run(RunOptions(selector=payload.selector, node_ids=payload.node_ids, trigger=payload.trigger))
    finally:
        RUN_LOCK.release()
    return record.model_dump()


@app.get("/api/runs")
def list_runs(limit: int = 20) -> dict[str, Any]:
    records = store.list_runs(limit=limit)
    return {
        "runs": [
            {
                "id": r.id,
                "created_at": r.created_at,
                "trigger": r.trigger,
                "status": r.status,
                "total": r.total,
                "passed": r.passed,
                "failed": r.failed,
                "duration": r.duration,
                "pass_rate": r.pass_rate,
                "report_path": r.report_path,
            }
            for r in records
        ]
    }


@app.get("/api/runs/{run_id}")
def get_run(run_id: int) -> dict[str, Any]:
    record = store.get_run(run_id)
    if not record:
        raise HTTPException(status_code=404, detail="运行不存在")
    return record.model_dump()


@app.get("/api/runs/{run_id}/report")
def get_report(run_id: int):
    record = store.get_run(run_id)
    if not record or not record.report_path:
        raise HTTPException(status_code=404, detail="报告不存在")
    path = ROOT / record.report_path
    if not path.exists():
        raise HTTPException(status_code=404, detail="报告文件已被清理")
    return FileResponse(path, media_type="text/html")


@app.get("/api/runs/{run_id}/triage")
def get_triage(run_id: int, llm: bool = False) -> dict[str, Any]:
    record = store.get_run(run_id)
    if not record:
        raise HTTPException(status_code=404, detail="运行不存在")
    results = triage_run(record, refine_with_llm=llm)
    return {
        "run_id": run_id,
        "distribution": distribution(results),
        "results": [item.model_dump() for item in results],
    }


@app.get("/api/schedule")
def get_schedule() -> dict[str, Any]:
    return scheduler.status()


@app.post("/api/schedule")
def set_schedule(payload: ScheduleRequest) -> dict[str, Any]:
    scheduler.reconfigure(enabled=payload.enabled, interval=payload.interval, selector=payload.selector)
    return scheduler.status()


# ---------------- 纪律检查 & 定位医生 ----------------
@app.get("/api/lint")
def lint_get() -> dict[str, Any]:
    return _lint_result(None, None)


@app.post("/api/lint")
def lint_post(payload: LintRequest) -> dict[str, Any]:
    return _lint_result(payload.tests_dir, payload.pages_dir)


def _lint_result(tests_dir: str | None, pages_dir: str | None) -> dict[str, Any]:
    violations = lint.check(
        tests_dir=Path(tests_dir) if tests_dir else None,
        pages_dir=Path(pages_dir) if pages_dir else None,
    )
    return {
        "ok": not violations,
        "counts": lint.summary(violations),
        "violations": [item.model_dump() for item in violations],
    }


@app.post("/api/doctor")
def doctor(payload: DoctorRequest) -> dict[str, Any]:
    html = payload.html
    if not html:
        if not payload.url:
            raise HTTPException(status_code=400, detail="html 与 url 至少给一个")
        try:
            html = locator_doctor.fetch_snapshot(payload.url)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=f"快照获取失败：{exc}") from exc
    candidates = locator_doctor.propose(payload.locator, html)
    return {"old": payload.locator, "candidates": [item.model_dump() for item in candidates]}


# ---------------- 前端 ----------------
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/")
def index():
    page = STATIC_DIR / "index.html"
    if page.exists():
        return FileResponse(page, media_type="text/html")
    return JSONResponse({"detail": "前端未构建"}, status_code=404)


settings.ensure_dirs()
app.mount("/artifacts", StaticFiles(directory=str(settings.artifacts_dir)), name="artifacts")