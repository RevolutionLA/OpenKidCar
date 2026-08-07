#!/usr/bin/env python3
"""CDP 检查：读取页面 DOM 关键指标（滚动高度、元素状态），用于验证布局。
用法：cdp_check.py <url> [等待秒] [宽] [高] [mobile]
"""
import asyncio
import json
import sys

import aiohttp

CDP = "http://127.0.0.1:9222"


async def main():
    url = sys.argv[1]
    wait = float(sys.argv[2]) if len(sys.argv) > 2 else 6.0
    width = int(sys.argv[3]) if len(sys.argv) > 3 else 1280
    height = int(sys.argv[4]) if len(sys.argv) > 4 else 800
    mobile = int(sys.argv[5]) if len(sys.argv) > 5 else 0

    async with aiohttp.ClientSession() as sess:
        async with sess.put(f"{CDP}/json/new?{url}") as r:
            tab = await r.json()
        ws_url = tab["webSocketDebuggerUrl"]
        async with sess.ws_connect(ws_url) as ws:
            await ws.send_str(json.dumps({
                "id": 1, "method": "Emulation.setDeviceMetricsOverride",
                "params": {"width": width, "height": height,
                           "deviceScaleFactor": 1, "mobile": bool(mobile)},
            }))
            await asyncio.sleep(wait)

            js = """(() => {
              const out = {
                innerH: window.innerHeight,
                scrollH: document.documentElement.scrollHeight,
                bodyScrollH: document.body.scrollHeight,
                oneScreen: document.documentElement.scrollHeight <= window.innerHeight + 2,
                speed: document.getElementById('speed') ? document.getElementById('speed').textContent : null,
                battery: document.getElementById('d-bat') ? document.getElementById('d-bat').textContent : null,
              };
              const rv = document.querySelector('.ring-val');
              if (rv) {
                out.ringDashOffset = rv.style.strokeDashoffset;
                out.ringDashArray = rv.getAttribute('stroke-dasharray');
              }
              const nd = document.getElementById('needle');
              if (nd) out.needleTransform = nd.style.transform;
              out.panels = {};
              document.querySelectorAll('.panel, .card').forEach(p => {
                const r = p.getBoundingClientRect();
                out.panels[p.className.split(' ')[0]] = {
                  top: Math.round(r.top), bottom: Math.round(r.bottom),
                  left: Math.round(r.left), right: Math.round(r.right),
                  h: Math.round(r.height)
                };
              });
              return JSON.stringify(out);
            })()"""
            await ws.send_str(json.dumps({
                "id": 2, "method": "Runtime.evaluate",
                "params": {"expression": js, "returnByValue": True},
            }))
            while True:
                m = await ws.receive()
                if m.type == aiohttp.WSMsgType.TEXT:
                    d = json.loads(m.data)
                    if d.get("id") == 2:
                        print(json.dumps(d["result"]["result"].get("value"),
                                         ensure_ascii=False, indent=2))
                        return


if __name__ == "__main__":
    asyncio.run(main())
