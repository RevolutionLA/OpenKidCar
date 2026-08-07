#!/usr/bin/env python3
"""端到端小智对话测试：模拟小车端网页 → twin_server(8000) → 桥接 → 小智 → 回复回网页。
用法：.venv/Scripts/python.exe tools/test_xiaozhi_e2e.py
"""
import asyncio
import base64
import json

import aiohttp


async def main():
    print("连接小车端 WS (localhost:8000/ws)…")
    async with aiohttp.ClientSession() as sess:
        ws = await sess.ws_connect("ws://localhost:8000/ws")
        # 等一个 state 确认连上
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT and json.loads(msg.data).get("type") == "state":
                print("已连接小车端 ✅")
                break

        # 1. 发 start
        await ws.send_str(json.dumps({"type": "xiaozhi", "action": "start"}))
        print("已发 start")

        # 2. 发 3 秒静音 PCM
        sr = 16000
        pcm = bytearray(sr * 3 * 2)
        chunk = sr // 2 * 2
        for i in range(0, len(pcm), chunk):
            b64 = base64.b64encode(bytes(pcm[i:i + chunk])).decode()
            await ws.send_str(json.dumps({"type": "xiaozhi", "action": "audio", "data": b64}))
            await asyncio.sleep(0.05)
        print("已发 3s 静音")

        # 3. 发 stop
        await ws.send_str(json.dumps({"type": "xiaozhi", "action": "stop"}))
        print("已发 stop，等待小智回复…")

        # 4. 收回复（经 twin_server 转发）
        reply_chunks = 0
        reply_bytes = 0
        async with asyncio.timeout(30):
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    d = json.loads(msg.data)
                    t = d.get("type")
                    if t == "xiaozhi_reply":
                        n = len(base64.b64decode(d.get("data", "")))
                        reply_chunks += 1
                        reply_bytes += n
                        print(f"  收到回复块: {n}B (累计 {reply_bytes})")
                        if reply_bytes > 10000:
                            break
                    elif t == "xiaozhi_log":
                        print(f"  [小智] {d.get('text')}")

        print(f"\n{'✅ 端到端链路通！共 ' + str(reply_chunks) + ' 块 / ' + str(reply_bytes) + ' 字节' if reply_bytes else '⚠️ 未收到回复'}")
        await ws.close()


if __name__ == "__main__":
    asyncio.run(main())
