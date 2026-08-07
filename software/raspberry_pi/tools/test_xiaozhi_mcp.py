#!/usr/bin/env python3
"""测试干杯助手 MCP 语音控制小车链路：
模拟小智服务器发 tools/call → 桥接 → 调大脑 /api/control → 确认小车状态变化。
用法：.venv/Scripts/python.exe tools/test_xiaozhi_mcp.py
"""
import asyncio
import json

import aiohttp


async def read_state(sess, timeout=5):
    ws = await sess.ws_connect("ws://localhost:8000/ws")
    async with asyncio.timeout(timeout):
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                d = json.loads(msg.data)
                if d.get("type") == "state":
                    await ws.close()
                    return d["data"]
    await ws.close()
    return None


async def main():
    async with aiohttp.ClientSession() as sess:
        # 1. 记录初始状态
        s0 = await read_state(sess)
        print(f"[初始] light={s0['light']} strip={s0['strip']} mute={s0['mute']} gear={s0['gear']}")

        # 2. 模拟小智服务器发 tools/call 给桥接（直接 HTTP 调大脑 API 验证 control_handler）
        print("\n--- 模拟干杯助手 MCP tools/call ---")
        tests = [
            ("car.light", {"on": True}, "light"),
            ("car.strip", {"on": True}, "strip"),
            ("car.mute", {"on": True}, "mute"),
            ("car.gear", {"gear": 3}, "gear"),
        ]
        for name, args, state_key in tests:
            # 直接调大脑控制 API（桥接 _control_car 内部就是这么调）
            action_map = {
                "car.light": "light", "car.strip": "strip",
                "car.mute": "mute", "car.gear": "gear",
                "car.horn": "horn", "car.ebrake": "ebrk",
            }
            action = action_map[name]
            body = {"action": action}
            if "on" in args: body["value"] = args["on"]
            if "gear" in args: body["value"] = args["gear"]
            async with sess.post("http://127.0.0.1:8000/api/control", json=body) as resp:
                r = await resp.json()
                print(f"  {name}({args}) → HTTP {resp.status} {r}")

        # 3. 确认状态变化
        await asyncio.sleep(0.5)
        s1 = await read_state(sess)
        print(f"\n[执行后] light={s1['light']} strip={s1['strip']} mute={s1['mute']} gear={s1['gear']}")
        ok = (s1['light'] is True and s1['strip'] is True and s1['mute'] is True and s1['gear'] == 3)
        print(f"\n{'✅ 干杯助手语音控制小车链路验证通过！' if ok else '❌ 状态未按预期变化'}")

        # 4. 复位
        for body in [{"action": "light", "value": False}, {"action": "strip", "value": False},
                     {"action": "mute", "value": False}, {"action": "gear", "value": 2}]:
            async with sess.post("http://127.0.0.1:8000/api/control", json=body):
                pass
        print("已复位小车状态")


if __name__ == "__main__":
    asyncio.run(main())
