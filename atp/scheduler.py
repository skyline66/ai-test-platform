"""定时冒烟：平台的第一性需求不是「功能多」，是「每天有人跑、挂了有人知道」。

刻意不用 APScheduler：一条 while 循环 + Event 足够，少一个依赖少一个坑。
"""
from __future__ import annotations

import threading
from datetime import datetime, timedelta

from atp import store
from atp.config import settings
from atp.models import now_iso
from atp.runner import RUN_LOCK, RunOptions, run

TICK_SECONDS = 5


class Scheduler:
    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._enabled = settings.schedule_enabled
        self._interval = settings.schedule_interval
        self._selector = settings.schedule_selector
        self._next_run: datetime | None = None
        self._last: dict = store.get_kv("schedule_last", {}) or {}
        self._load_persisted()

    # ---------- 配置持久化 ----------
    def _load_persisted(self) -> None:
        saved = store.get_kv("schedule_config")
        if isinstance(saved, dict):
            self._enabled = bool(saved.get("enabled", self._enabled))
            self._interval = int(saved.get("interval", self._interval))
            self._selector = str(saved.get("selector", self._selector))

    def _persist(self) -> None:
        store.set_kv(
            "schedule_config",
            {"enabled": self._enabled, "interval": self._interval, "selector": self._selector},
        )

    # ---------- 生命周期 ----------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._next_run = datetime.now() + timedelta(seconds=self._interval)
        self._thread = threading.Thread(target=self._loop, name="atp-scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=TICK_SECONDS + 1)
        self._thread = None

    def reconfigure(self, *, enabled: bool | None = None, interval: int | None = None, selector: str | None = None) -> None:
        if enabled is not None:
            self._enabled = enabled
        if interval is not None:
            self._interval = max(60, interval)
        if selector is not None:
            self._selector = selector
        if self._enabled:
            self._next_run = datetime.now() + timedelta(seconds=self._interval)
            self.start()
        self._persist()

    # ---------- 主循环 ----------
    def _loop(self) -> None:
        while not self._stop.wait(TICK_SECONDS):
            if not self._enabled:
                continue
            if self._next_run and datetime.now() < self._next_run:
                continue
            self._next_run = datetime.now() + timedelta(seconds=self._interval)
            self._run_once()

    def _run_once(self) -> None:
        if not RUN_LOCK.acquire(blocking=False):
            self._last = {**self._last, "skipped": "上一次运行还没结束", "skipped_at": now_iso()}
            return
        try:
            record = run(RunOptions(selector=self._selector, trigger="schedule"))
            self._last = {
                "run_id": record.id,
                "status": record.status,
                "failed": record.failed,
                "total": record.total,
                "at": record.created_at,
            }
            store.set_kv("schedule_last", self._last)
        except Exception as exc:  # noqa: BLE001 - 定时任务不能因为一次异常就死掉
            self._last = {**self._last, "error": str(exc), "at": now_iso()}
            store.set_kv("schedule_last", self._last)
        finally:
            RUN_LOCK.release()

    # ---------- 状态 ----------
    def status(self) -> dict:
        return {
            "enabled": self._enabled,
            "interval": self._interval,
            "selector": self._selector,
            "next_run_at": self._next_run.isoformat(timespec="seconds") if self._next_run and self._enabled else None,
            "last": self._last,
            "thread_alive": bool(self._thread and self._thread.is_alive()),
        }


scheduler = Scheduler()