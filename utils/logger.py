"""日志：一条用例一次文件，挂的时候能对着时间线复盘。"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from utils.config import settings

_CONFIGURED = False


def _configure() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    settings.log_dir.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)-5s [%(name)s] %(message)s", "%H:%M:%S")

    file_handler = logging.FileHandler(settings.log_dir / "test.log", encoding="utf-8")
    file_handler.setFormatter(fmt)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(fmt)

    root = logging.getLogger("atp")
    root.setLevel(logging.INFO)
    root.addHandler(file_handler)
    root.addHandler(stream_handler)
    root.propagate = False
    _CONFIGURED = True


def get_logger(name: str = "atp") -> logging.Logger:
    _configure()
    return logging.getLogger(f"atp.{name}")


def log_path() -> Path:
    return settings.log_dir / "test.log"