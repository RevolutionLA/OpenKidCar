#!/usr/bin/env python3
"""CDP 截图：真实等待 WS 连接后再截图，用于验证前端渲染（绕开 --virtual-time-budget 饿死 WS 的坑）。
用法：cdp_shot.py <url> <输出png> [等待秒] [宽] [高] [mobile 0/1]
"""
import asyncio
import base64
import json
import sys

import aiohttp

CDP = "http://127.0.0.1:9222"


async def main():
    url = sys.argv[1]
    out = sys.argv[2]
    wait = float(sys.argv[3]) if len(sys.argv) > 3 else 6.0
    width = int(sys.argv[4]) if len(sys.argv) > 4 else 1280
    height = int(sys.argv[5]) if len(sys.argv) > 5 else 800
    mobile = int(sys.argv[6]) if len(sys.argv) > 6 else 0

    async with aiohttp.ClientSession() as sess:
        # 打开新标签页
        async with sess.put(f"{CDP}/json/new?{url}") as r:
            tab = await r.json()
        ws_url = tab["webSocketDebuggerUrl"]
        print(f"标签页: {ws_url}", flush=True)

        async with sess.ws_connect(ws_url) as ws:
            # 设置视口
            await ws.send_str(json.dumps({
                "id": 1, "method": "Emulation.setDeviceMetricsOverride",
                "params": {"width": width, "height": height,
                           "deviceScaleFactor": 1, "mobile": bool(mobile)},
            }))
            await asyncio.sleep(wait)  # 真实等待，让 WS 连接并渲染数据

            await ws.send_str(json.dumps({"id": 2, "method": "Page.captureScreenshot",
                                          "params": {"format": "png"}}))
            while True:
                m = await ws.receive()
                if m.type == aiohttp.WSMsgType.TEXT:
                    d = json.loads(m.data)
                    if d.get("id") == 2:
                        img = base64.b64decode(d["result"]["data"])
                        with open(out, "wb") as f:
                            f.write(img)
                        print(f"✅ 截图已保存: {out} ({len(img)}B)", flush=True)
                        return


if __name__ == "__main__":
    asyncio.run(main())
