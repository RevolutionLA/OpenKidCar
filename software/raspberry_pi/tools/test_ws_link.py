#!/usr/bin/env python3
"""端到端验证双端 WS 通信链路（不依赖浏览器/摄像头）：
  家长端发 call → 小车端应收到；小车端发 audio/video → 家长端应收到；
  家长端发 remote_ebrk → 小车端应收到急刹状态。
"""
import asyncio
import json
import sys

import aiohttp


async def recv_until(ws, want_type, timeout=5.0):
    """从 ws 持续读消息，直到遇到指定 type 的消息。"""
    async with asyncio.timeout(timeout):
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    d = json.loads(msg.data)
                except Exception:
                    continue
                if d.get("type") == want_type:
                    return d
    return None


async def main():
    sess = aiohttp.ClientSession()
    ok = True

    print("连接小车端 WS (8000/ws) 和家长端 WS (8001/ws)…")
    kid = await sess.ws_connect("ws://localhost:8000/ws")
    parent = await sess.ws_connect("ws://localhost:8001/ws")

    # 1. 两端都应收到状态快照（同一辆车）
    s1 = await recv_until(kid, "state")
    s2 = await recv_until(parent, "state")
    print(f"[1] 小车端状态: speed={s1['data']['speed']} bat={s1['data']['battery_pct']:.0f}%")
    print(f"[1] 家长端状态: speed={s2['data']['speed']} bat={s2['data']['battery_pct']:.0f}%")
    same = s1["data"]["speed"] == s2["data"]["speed"] and \
        abs(s1["data"]["battery_pct"] - s2["data"]["battery_pct"]) < 1
    print(f"    双端状态一致: {'✅' if same else '❌'}")

    # 2. 家长端发 call → 小车端应收到
    await parent.send_str(json.dumps({"type": "call"}))
    c = await recv_until(kid, "call")
    print(f"[2] 家长端 call → 小车端收到: {'✅' if c and c.get('from') == 'parent' else '❌'}")

    # 3. 小车端发 video → 家长端应收到
    await kid.send_str(json.dumps({"type": "video", "from": "kid",
                                   "data": "data:image/jpeg;base64,FAKE"}))
    v = await recv_until(parent, "video")
    print(f"[3] 小车端 video → 家长端收到: {'✅' if v else '❌'}")

    # 4. 小车端发 audio → 家长端应收到
    await kid.send_str(json.dumps({"type": "audio", "from": "kid",
                                   "data": "data:audio/webm;base64,FAKE"}))
    a = await recv_until(parent, "audio")
    print(f"[4] 小车端 audio → 家长端收到: {'✅' if a else '❌'}")

    # 5. 家长端发 remote_ebrk → 小车端应收到急刹状态（state 里 ebrk=True）
    await parent.send_str(json.dumps({"type": "remote_ebrk"}))
    e = await recv_until(kid, "state")
    ebrk_ok = e and e["data"]["ebrk"] is True
    print(f"[5] 家长端远程急刹 → 小车端状态 ebrk=True: {'✅' if ebrk_ok else '❌'}")

    # 6. 小车端发命令（档位）→ 家长端应看到状态变化（等几帧）
    await kid.send_str(json.dumps({"type": "gear", "value": 3}))
    gear_ok = False
    for _ in range(80):  # 最多等 80 个 state（约 1.6s）
        g = await recv_until(parent, "state", timeout=2.0)
        if g and g["data"]["gear"] == 3:
            gear_ok = True
            break
    print(f"[6] 小车端设档位 D3 → 家长端状态 gear=3: {'✅' if gear_ok else '❌'}")

    await kid.close(); await parent.close(); await sess.close()
    print("\n全部链路验证完成 ✅" if ok else "\n存在失败 ❌")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"测试异常: {e}")
        sys.exit(1)
