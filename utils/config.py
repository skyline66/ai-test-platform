"""配置层：只负责「读」，不做业务判断。

优先级：环境变量 > .env > 默认值。被测地址留空时，conftest 会拉起内置 demo_app。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    """极简 .env 读取，避免为一行配置装一个依赖。"""
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


@dataclass(frozen=True)
class Settings:
    base_url: str = ""
    artifacts_dir: Path = field(default_factory=lambda: ROOT / "artifacts")
    evidence_dir: Path = field(default_factory=lambda: ROOT / "artifacts" / "evidence")
    log_dir: Path = field(default_factory=lambda: ROOT / "artifacts" / "logs")
    headless: bool = True

    @property
    def has_remote_env(self) -> bool:
        return bool(self.base_url)


def get_settings() -> Settings:
    _load_dotenv()
    artifacts = Path(os.getenv("ATP_ARTIFACTS", "artifacts"))
    if not artifacts.is_absolute():
        artifacts = ROOT / artifacts
    return Settings(
        base_url=os.getenv("ATP_BASE_URL", "").rstrip("/"),
        artifacts_dir=artifacts,
        evidence_dir=artifacts / "evidence",
        log_dir=artifacts / "logs",
        headless=os.getenv("ATP_HEADED", "0") != "1",
    )


settings = get_settings()