#!/usr/bin/env python3
"""干杯一号 · 数字孪生 —— 本地 Web 服务器。

用 Python 标准库提供服务（零依赖），把 frontend 目录作为网站根目录。
浏览器打开 http://localhost:8000 即可进入数字孪生驾驶舱。

运行：
  python serve.py [端口]       默认 8000
"""

import os
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler

FRONTEND = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend")
)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=FRONTEND, **kwargs)

    def log_message(self, fmt, *args):
        print(f"[{self.log_date_time_string()}] {args[0]}")


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    server = HTTPServer(("localhost", port), Handler)
    print("=" * 52)
    print("  🚗 干杯一号 · 数字孪生驾驶舱")
    print(f"  打开浏览器:  http://localhost:{port}")
    print("  按 Ctrl+C 停止")
    print("=" * 52)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务器已停止")
        server.server_close()


if __name__ == "__main__":
    main()
