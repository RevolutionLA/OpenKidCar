#!/usr/bin/env python3
"""测试倒车 R 档完整链路：设 R → 速度变负 → GPS 反向移动。
用法：.venv/Scripts/python.exe tools/test_reverse.py
"""
import asyncio
import json

import aiohttp


async def get_state(ws, want=None, timeout=6):
    async with asyncio.timeout(timeout):
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                d = json.loads(msg.data)
                if d.get("type") == "state":
                    s = d["data"]
                    if want is None or want(s):
                        return s
    return None


async def main():
    async with aiohttp.ClientSession() as sess:
        kws = await sess.ws_connect("ws://localhost:8000/ws")

        # 1. 设 R 档（-1）
        await kws.send_str(json.dumps({"type": "gear", "value": -1}))
        s = await get_state(kws, lambda s: s["gear"] == -1)
        print(f"[1] 设 R 档→ gear={s['gear']} {'✅' if s and s['gear']==-1 else '❌'}")

        # 2. 踩油门，速度应为负
        await kws.send_str(json.dumps({"type": "throttle", "value": 80}))
        s = await get_state(kws, lambda s: s["speed"] < -0.1)
        print(f"[2] R档踩油门→ speed={s['speed']:.1f} (负=倒车) {'✅' if s and s['speed']<0 else '❌'}")

        # 3. 记录倒车前 GPS，确认反向移动
        s1 = await get_state(kws, lambda s: s["speed"] < -0.1)
        g1 = s1["gps"]
        await asyncio.sleep(1.5)
        s2 = await get_state(kws, lambda s: abs(s["gps"]["lat"] - g1["lat"]) > 1e-6)
        g2 = s2["gps"]
        moved = abs(g2["lat"] - g1["lat"]) > 1e-7 or abs(g2["lng"] - g1["lng"]) > 1e-7
        print(f"[3] 倒车GPS移动→ lat {g1['lat']}→{g2['lat']} {'✅' if moved else '❌'}")

        # 4. 复位：回 D2、油门 0
        await kws.send_str(json.dumps({"type": "gear", "value": 2}))
        await kws.send_str(json.dumps({"type": "throttle", "value": 0}))
        s = await get_state(kws, lambda s: s["gear"] == 2 and s["speed"] > -0.1)
        print(f"[4] 复位→ gear={s['gear']} speed={s['speed']:.1f} {'✅' if s else '❌'}")

        await kws.close()


if __name__ == "__main__":
    asyncio.run(main())
