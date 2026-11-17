"""内置演示站服务器：让整个平台离线可跑。

真实项目里这段会被换成「环境配置」（测试环境 / 预发 / 灰度），
但「环境必须可复现」这条要求是一样的，所以这里也把端口、时区、目录固定下来。
"""
from __future__ import annotations

import functools
import socket
import threading
from contextlib import contextmanager
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator

from utils.config import ROOT
from utils.logger import get_logger

DEMO_APP_DIR = ROOT / "demo_app"
log = get_logger("demo_server")


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:  # noqa: A003 - 屏蔽逐请求打屏
        log.debug("demo %s", fmt % args)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@contextmanager
def demo_server(port: int | None = None) -> Iterator[str]:
    """启动演示站，产出 base_url；退出时必定关掉，不留残留端口。"""
    port = port or free_port()
    handler = functools.partial(_QuietHandler, directory=str(DEMO_APP_DIR))
    httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    httpd.daemon_threads = True

    thread = threading.Thread(target=httpd.serve_forever, name="demo-server", daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{port}"
    log.info("演示站已启动：%s", base_url)

    try:
        yield base_url
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
        log.info("演示站已关闭")


if __name__ == "__main__":  # 手动起站：python -m utils.demo_server
    with demo_server(port=8811) as url:
        log.info("按 Ctrl+C 退出。登录页：%s/index.html", url)
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass