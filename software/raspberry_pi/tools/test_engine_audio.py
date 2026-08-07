#!/usr/bin/env python3
"""验证引擎声 engineAudio 的 volume/playbackRate 随油门/刹车/急刹变化。"""
import asyncio
import json

import aiohttp

CDP = "http://127.0.0.1:9222"
BUS = "ws://localhost:8000/ws"


async def cdp_eval(ws, expr, mid):
    await ws.send_str(json.dumps({"id": mid, "method": "Runtime.evaluate",
                                  "params": {"expression": expr, "returnByValue": True}}))
    while True:
        m = await ws.receive()
        if m.type == aiohttp.WSMsgType.TEXT:
            d = json.loads(m.data)
            if d.get("id") == mid:
                return d["result"]["result"].get("value")


async def main():
    async with aiohttp.ClientSession() as sess:
        # 打开小车端页面
        async with sess.put(f"{CDP}/json/new?http://localhost:8000/") as r:
            tab = await r.json()
        cws = await sess.ws_connect(tab["webSocketDebuggerUrl"])
        # 等页面 JS 完全加载（bindToggle 绑定后）再点击触发 initAudio
        await asyncio.sleep(6)
        await cdp_eval(cws, "document.getElementById('sw-light').click(); 'clicked'", 1)
        for _ in range(10):
            await asyncio.sleep(1)
            has = await cdp_eval(cws, "window.engineAudio ? 'yes' : 'no'", 90)
            if has == "yes":
                break
        await asyncio.sleep(2)
        # 读 engineAudio 初始状态
        init = await cdp_eval(cws, "window.engineAudio ? JSON.stringify({vol: window.engineAudio.volume.toFixed(3), rate: window.engineAudio.playbackRate.toFixed(2), paused: window.engineAudio.paused, ready: window.engineAudio.readyState}) : 'no engineAudio'", 2)
        print(f"初始(油门0): {init}")

        # 业务 WS 发油门
        bus = await sess.ws_connect(BUS)
        async def send_cmd(obj):
            await bus.send_str(json.dumps(obj))
            await asyncio.sleep(0.8)

        # 踩油门 80
        await send_cmd({"type": "throttle", "value": 80})
        s1 = await cdp_eval(cws, "window.engineAudio ? JSON.stringify({vol: window.engineAudio.volume.toFixed(3), rate: window.engineAudio.playbackRate.toFixed(2), paused: window.engineAudio.paused}) : 'no'", 3)
        print(f"油门80: {s1}")

        # 踩油门 100 再等速度上来
        await send_cmd({"type": "throttle", "value": 100})
        await asyncio.sleep(3)
        s2 = await cdp_eval(cws, "window.engineAudio ? JSON.stringify({vol: window.engineAudio.volume.toFixed(3), rate: window.engineAudio.playbackRate.toFixed(2), paused: window.engineAudio.paused}) : 'no'", 4)
        print(f"油门100+速度上升: {s2}")

        # 深刹车 100
        await send_cmd({"type": "brake", "value": 100})
        s3 = await cdp_eval(cws, "window.engineAudio ? JSON.stringify({vol: window.engineAudio.volume.toFixed(3), rate: window.engineAudio.playbackRate.toFixed(2), paused: window.engineAudio.paused}) : 'no'", 5)
        print(f"刹车100: {s3}")

        # 急刹
        await send_cmd({"type": "btn", "name": "EBRK_BTN"})
        s4 = await cdp_eval(cws, "window.engineAudio ? JSON.stringify({vol: window.engineAudio.volume.toFixed(3), rate: window.engineAudio.playbackRate.toFixed(2), paused: window.engineAudio.paused}) : 'no'", 6)
        print(f"急刹ON: {s4}")

        # 恢复：油门0
        await send_cmd({"type": "throttle", "value": 0})
        await send_cmd({"type": "brake", "value": 0})
        s5 = await cdp_eval(cws, "window.engineAudio ? JSON.stringify({vol: window.engineAudio.volume.toFixed(3), rate: window.engineAudio.playbackRate.toFixed(2), paused: window.engineAudio.paused}) : 'no'", 7)
        print(f"复位油门0刹车0: {s5}")

        await bus.close(); await cws.close()


if __name__ == "__main__":
    asyncio.run(main())
