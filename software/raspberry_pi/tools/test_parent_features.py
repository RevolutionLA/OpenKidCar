#!/usr/bin/env python3
"""测试 P0/P1/P2 三项新功能：家长设档位、上下电、轨迹回放数据。
用法：.venv/Scripts/python.exe tools/test_parent_features.py
"""
import asyncio
import json

import aiohttp


async def get_state(ws, want=None, timeout=5):
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
        pws = await sess.ws_connect("ws://localhost:8001/ws")
        kws = await sess.ws_connect("ws://localhost:8000/ws")

        s0 = await get_state(pws)
        print(f"[初始] gear={s0['gear']} seat={s0['seat']} hist={len(s0.get('gps_history', []))}")

        # 1. 家长设档位 → 3
        await pws.send_str(json.dumps({"type": "gear", "value": 3}))
        s = await get_state(pws, lambda s: s["gear"] == 3)
        print(f"[1] 家长设档位→ gear={s['gear']} {'✅' if s and s['gear']==3 else '❌'}")

        # 2. 上电 → True
        await pws.send_str(json.dumps({"type": "seat", "value": True}))
        s = await get_state(pws, lambda s: s["seat"] is True)
        print(f"[2] 上电→ seat={s['seat']} {'✅' if s and s['seat'] else '❌'}")

        # 3. 下电 → False
        await pws.send_str(json.dumps({"type": "seat", "value": False}))
        s = await get_state(pws, lambda s: s["seat"] is False)
        print(f"[3] 下电→ seat={s['seat']} {'✅' if s and not s['seat'] else '❌'}")

        # 4. 小车跑起来生成轨迹
        await kws.send_str(json.dumps({"type": "throttle", "value": 80}))
        await asyncio.sleep(2)
        await kws.send_str(json.dumps({"type": "throttle", "value": 0}))
        await asyncio.sleep(0.3)
        s = await get_state(pws, lambda s: len(s.get("gps_history", [])) > 0)
        n = len(s.get("gps_history", [])) if s else 0
        print(f"[4] 轨迹历史点数={n} {'✅' if n > 0 else '❌'}")
        if s and n:
            print(f"    最新点: {s['gps_history'][-1]}")

        await kws.close()
        await pws.close()


if __name__ == "__main__":
    asyncio.run(main())
