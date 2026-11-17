"""平台数据模型：一条运行、一个用例、一次归因，都是可序列化的对象。"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class FailureClass(str, Enum):
    """归因分类。前四类是环境/脚本问题，后几类才是产品或数据问题。"""

    SELECTOR_NOT_FOUND = "selector_not_found"
    TIMEOUT = "timeout"
    ASSERTION = "assertion"
    ENV_MISMATCH = "env_mismatch"
    NETWORK = "network"
    AUTH = "auth"
    DATA = "data"
    FLAKY = "flaky"
    APP_BUG = "app_bug"
    UNKNOWN = "unknown"


class CaseRef(BaseModel):
    """用例管理的最小单元：能列出、能勾选、能定位到文件行。"""

    nodeid: str                      # tests/test_login.py::test_login_success
    title: str                       # 人话标题（有 allure.title 就用它）
    file: str
    line: int = 0
    markers: list[str] = Field(default_factory=list)
    fixtures: list[str] = Field(default_factory=list)
    has_browser: bool = False


class CaseResult(BaseModel):
    nodeid: str
    title: str = ""
    outcome: str = "unknown"         # passed / failed / skipped / error
    duration: float = 0.0
    error_text: str = ""
    failure_class: FailureClass | None = None
    failure_reason: str = ""
    screenshot: str = ""             # 相对 run 目录
    evidence_url: str = ""
    console: list[str] = Field(default_factory=list)

    @property
    def failed(self) -> bool:
        return self.outcome in {"failed", "error"}


class RunRecord(BaseModel):
    id: int = 0
    created_at: str = Field(default_factory=now_iso)
    trigger: str = "manual"          # manual / schedule / api
    selector: str = ""
    status: str = "running"          # running / passed / failed / error
    duration: float = 0.0
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    pass_rate: float = 0.0
    report_path: str = ""
    exit_code: int = 0
    stdout_tail: str = ""
    cases: list[CaseResult] = Field(default_factory=list)

    @property
    def failed_cases(self) -> list[CaseResult]:
        return [c for c in self.cases if c.failed]


class TriageResult(BaseModel):
    nodeid: str
    title: str = ""
    failure_class: FailureClass = FailureClass.UNKNOWN
    confidence: float = 0.0
    reason: str = ""
    suggestion: str = ""
    source: str = "rule"              # rule / llm


class DraftResult(BaseModel):
    requirement: str
    provider: str = "template"        # template / llm
    files: dict[str, str] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
    valid: bool = False
    errors: list[str] = Field(default_factory=list)
    written: list[str] = Field(default_factory=list)


class Violation(BaseModel):
    rule: str
    file: str
    line: int
    snippet: str
    hint: str


class LocatorCandidate(BaseModel):
    locator: str
    kind: str                        # button / link / input / text
    name: str
    score: float = 0.0


class SystemInfo(BaseModel):
    python: str = ""
    playwright: str = ""
    browser: str = ""
    timezone: str = ""
    platform: str = ""
    base_url: str = ""
    demo_mode: bool = True
    llm_enabled: bool = False
    llm_model: str = ""
    artifacts: str = ""
    extra: dict[str, Any] = Field(default_factory=dict)