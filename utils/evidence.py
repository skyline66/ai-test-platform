"""现场保全：失败时挂三样东西 —— 截图、当前 URL、控制台日志。

文章里那句「报告的价值不在通过率，在挂了能不能一眼看出挂在哪」，
落到代码上就是这个文件。它只做一件事，且必须在 page 关闭前调用。
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from utils.config import settings

_SAFE = re.compile(r"[^0-9A-Za-z_.-]+")


def safe_name(nodeid: str) -> str:
    """把 pytest nodeid 变成文件名，保证平台侧能反查回用例。"""
    return _SAFE.sub("_", nodeid).strip("_")[:160]


def capture(
    page: Any,
    nodeid: str,
    console_logs: Sequence[str] | None = None,
    base_url: str = "",
) -> dict[str, Any]:
    """保存现场并返回索引；任何一步失败都不应把原异常顶掉。"""
    settings.evidence_dir.mkdir(parents=True, exist_ok=True)
    stem = safe_name(nodeid)
    png_path = settings.evidence_dir / f"{stem}.png"
    json_path = settings.evidence_dir / f"{stem}.json"

    info: dict[str, Any] = {
        "nodeid": nodeid,
        "captured_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "base_url": base_url,
        "url": "",
        "title": "",
        "screenshot": "",
        "console": list(console_logs or []),
    }

    try:
        info["url"] = page.url
        info["title"] = page.title()
    except Exception:  # noqa: BLE001 - 现场保全不能反向影响测试结论
        pass

    try:
        page.screenshot(path=str(png_path), full_page=True)
        info["screenshot"] = png_path.name
    except Exception:  # noqa: BLE001
        pass

    try:
        json_path.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
        info["evidence_json"] = json_path.name
    except Exception:  # noqa: BLE001
        pass

    _attach_to_allure(info, png_path)
    return info


def _attach_to_allure(info: dict[str, Any], png_path: Path) -> None:
    """有 allure-pytest 就挂附件，没有也不影响流程。"""
    try:
        import allure
    except ImportError:
        return

    try:
        with allure.step("失败现场"):
            if png_path.exists():
                allure.attach(
                    png_path.read_bytes(),
                    name="失败截图",
                    attachment_type=allure.attachment_type.PNG,
                )
            allure.attach(
                f"URL: {info['url']}\n标题: {info['title']}\n\n"
                + "\n".join(info["console"][-50:]),
                name="URL与控制台日志",
                attachment_type=allure.attachment_type.TEXT,
            )
    except Exception:  # noqa: BLE001
        pass