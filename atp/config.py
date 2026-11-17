"""平台配置：所有可变量集中在这里，代码里不许再出现魔数。

环境变量前缀 ATP_，也可写进 .env（见 .env.example）。
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ATP_",
        env_file=str(ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # 被测环境：留空 = 用内置 demo_app
    base_url: str = ""

    # 目录
    artifacts: str = "artifacts"
    db_path: str = "artifacts/atp.db"
    tests_dir: str = "tests"
    pages_dir: str = "pages"

    # LLM（留空 = 离线降级）
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = "deepseek-chat"
    llm_timeout: int = 60

    # 调度
    schedule_enabled: bool = False
    schedule_interval: int = Field(default=3600, ge=60)
    schedule_selector: str = "-m smoke"

    # 服务
    host: str = "127.0.0.1"
    port: int = 8077

    # 单次运行超时（秒）
    run_timeout: int = 1800

    # ---------- 派生路径 ----------
    @property
    def artifacts_dir(self) -> Path:
        p = Path(self.artifacts)
        return p if p.is_absolute() else ROOT / p

    @property
    def runs_dir(self) -> Path:
        return self.artifacts_dir / "runs"

    @property
    def db_file(self) -> Path:
        p = Path(self.db_path)
        return p if p.is_absolute() else ROOT / p

    @property
    def tests_path(self) -> Path:
        return ROOT / self.tests_dir

    @property
    def pages_path(self) -> Path:
        return ROOT / self.pages_dir

    @property
    def base_url_value(self) -> str:
        return self.base_url.rstrip("/")

    @property
    def llm_ready(self) -> bool:
        return bool(self.llm_base_url and self.llm_api_key)

    def ensure_dirs(self) -> None:
        for path in (self.artifacts_dir, self.runs_dir, self.db_file.parent):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings


settings = get_settings()