#!/usr/bin/env python3
"""小智桥接消息流测试：连桥接 8010，发 start → 发一段正弦 PCM → stop，确认收到小智回复。
用法：.venv/Scripts/python.exe tools/test_xiaozhi_bridge.py
"""
import asyncio
import base64
import json
import math
import struct

import aiohttp


async def main():
    print("连接小智桥接 (127.0.0.1:8010/xiaozhi)…")
    async with aiohttp.ClientSession() as sess:
        ws = await sess.ws_connect("ws://127.0.0.1:8010/xiaozhi")
        print("已连接 ✅")

        # 1. 开始监听
        await ws.send_str(json.dumps({"type": "xiaozhi", "action": "start"}))
        print("已发送 start")

        # 2. 发一段静音（16kHz 静音 int16 最接近"无语音"，已验证能触发小智回复）
        sr = 16000
        pcm = bytearray(sr * 3 * 2)  # 3 秒静音，int16 = 2 字节/样本
        # 分帧发送（每 0.5 秒一帧）
        chunk = sr // 2 * 2  # 0.5s = 16000 字节
        for i in range(0, len(pcm), chunk):
            b64 = base64.b64encode(bytes(pcm[i:i + chunk])).decode()
            await ws.send_str(json.dumps({"type": "xiaozhi", "action": "audio", "data": b64}))
            await asyncio.sleep(0.05)
        print("已发送 3s 静音音频")

        # 3. 结束监听
        await ws.send_str(json.dumps({"type": "xiaozhi", "action": "stop"}))
        print("已发送 stop，等待小智回复…")

        # 4. 接收回复（最多 30 秒）
        reply_bytes = 0
        reply_chunks = 0
        async with asyncio.timeout(30):
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    d = json.loads(msg.data)
                    if d.get("type") == "xiaozhi_reply":
                        data = d.get("data", "")
                        n = len(base64.b64decode(data))
                        reply_bytes += n
                        reply_chunks += 1
                        print(f"  收到回复音频块: {n} 字节 (累计 {reply_bytes})")
                    elif d.get("type") == "xiaozhi_log":
                        print(f"  [小智] {d.get('text')}")
                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    break
                # 收到足够多回复就停
                if reply_bytes > 10000:
                    break

        if reply_bytes > 0:
            print(f"\n✅ 收到小智回复！共 {reply_chunks} 块 / {reply_bytes} 字节 PCM")
            print("（浏览器端会转成 <audio> 播放这段回复）")
        else:
            print("\n⚠️ 未收到小智回复（可能没识别出正弦波是人声，或服务器无响应）")

        await ws.close()


if __name__ == "__main__":
    asyncio.run(main())
