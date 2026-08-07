#!/usr/bin/env python3
"""抓取小智回复音频存成 WAV，用于音质分析。
用法：.venv/Scripts/python.exe tools/capture_xiaozhi_reply.py <out.wav>
"""
import asyncio
import base64
import json
import struct
import sys

import aiohttp


async def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "xiaozhi_reply.wav"
    print("连接小智桥接…")
    async with aiohttp.ClientSession() as sess:
        ws = await sess.ws_connect("ws://127.0.0.1:8010/xiaozhi")
        await ws.send_str(json.dumps({"type": "xiaozhi", "action": "start"}))

        # 发 2 秒"人声模拟"（基频+谐波，带音节起伏，更易触发 ASR 回复）
        sr = 16000
        samples = bytearray()
        for i in range(sr * 2):
            # 基频随"音节"起伏（120-180Hz），模拟说话
            syll = int(i / sr * 4)  # 每 0.25s 一个音节
            f = 120 + 60 * (0.5 - abs((i / sr * 4) % 1 - 0.5))
            val = int(6000 * (0.7 * __import__("math").sin(2 * __import__("math").pi * f * i / sr)
                              + 0.3 * __import__("math").sin(4 * __import__("math").pi * f * i / sr)))
            samples += struct.pack("<h", val)
        for i in range(0, len(samples), 16000):
            b64 = base64.b64encode(bytes(samples[i:i + 16000])).decode()
            await ws.send_str(json.dumps({"type": "xiaozhi", "action": "audio", "data": b64}))
            await asyncio.sleep(0.05)
        await ws.send_str(json.dumps({"type": "xiaozhi", "action": "stop"}))
        print("已发 2s 人声模拟，等待回复…")

        pcm_all = bytearray()
        async with asyncio.timeout(30):
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    d = json.loads(msg.data)
                    if d.get("type") == "xiaozhi_reply":
                        pcm_all += base64.b64decode(d.get("data", ""))
                        if len(pcm_all) > 500000:
                            break

        if not pcm_all:
            print("未收到回复！")
            return

        # 拼 WAV（16bit 单声道 24kHz）
        sr, ch, bits = 24000, 1, 16
        data_len = len(pcm_all)
        with open(out, "wb") as f:
            f.write(b"RIFF")
            f.write(struct.pack("<I", 36 + data_len))
            f.write(b"WAVEfmt ")
            f.write(struct.pack("<IHHIIHH", 16, 1, ch, sr, sr * ch * bits // 8, ch * bits // 8, bits))
            f.write(b"data")
            f.write(struct.pack("<I", data_len))
            f.write(bytes(pcm_all))
        print(f"✅ 已保存 {len(pcm_all)} 字节 PCM → {out} ({(len(pcm_all)/(sr*2)):.2f} 秒)")


if __name__ == "__main__":
    asyncio.run(main())
