#!/usr/bin/env python3
"""干杯一号 · 数字孪生后端（大脑 + 小脑真正协同）

一个进程同时提供：
  - HTTP 静态服务（数字孪生前端页面）
  - WebSocket（/ws）：前端 ↔ 后端实时双向通信
  - Brain（大脑）+ CerebellumSim（虚拟小脑）：内存管道按协议交互
  - VoiceController（vosk 语音识别，可选）：唤醒词"干杯出来"+ 指令

前端在浏览器操作 → WebSocket 命令 → 大脑决策 → 协议 → 小脑执行
→ 状态快照 → WebSocket 推送前端渲染车模。

运行（在 software/raspberry_pi 目录）：
  .venv/Scripts/python.exe digital_twin/backend/twin_server.py [端口]
  浏览器打开 http://localhost:8000
"""

import asyncio
import json
import os
import queue
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

from aiohttp import web

from car_brain.brain import Brain
from car_brain.serial_link import SerialLink
from car_brain.simulator import CerebellumSim, Pipe

FRONTEND = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend")
)


class TwinCore:
    """大脑 + 小脑核心，线程安全地向前端输出状态/事件。"""

    def __init__(self):
        # 内存管道连接大脑与小脑（与真实硬件同一套协议）
        self.bp, self.cp = Pipe(), Pipe()
        self.bp.peer, self.cp.peer = self.cp, self.bp
        self.ceb = CerebellumSim(self.cp)
        self.brain = Brain(SerialLink(self.bp))
        self.brain.on_event = self._on_brain_event
        self.brain.start()

        self.clients = set()
        self.outbox = queue.Queue()   # ("state"|"log", data)，由事件循环统一发送
        self.voice = None
        self.voice_on = False

    # ---------- 大脑事件 ----------
    def _on_brain_event(self, event, data):
        msgs = {
            "light": f"大灯 -> {'开' if data else '关'}",
            "mute": f"静音 -> {'开' if data else '关'}",
            "ebrk": "⚠️ 急刹触发！",
        }
        if event in msgs:
            self.log(msgs[event])

    # ---------- 命令入口（前端 WebSocket 消息） ----------
    def handle_command(self, msg):
        t = msg.get("type")
        if t == "btn":
            self.ceb.press_button(msg["name"])
        elif t == "throttle":
            self.ceb.set_throttle(msg["value"])
        elif t == "brake":
            self.ceb.set_brake(msg["value"])
        elif t == "gear":
            self.brain.set_gear(msg["value"])
        elif t == "steer":
            self.ceb.set_steer(msg["value"])
        elif t == "horn":
            self.ceb.set_horn(bool(msg["value"]))
        elif t == "voice":
            self.toggle_voice()

    # ---------- 语音识别（vosk） ----------
    def toggle_voice(self):
        if self.voice is None:
            try:
                from car_brain.voice import VoiceController
                self.voice = VoiceController()
                self.voice.on_command = self._voice_cmd
                self.voice.on_status = lambda t: self.log(f"[语音] {t}")
                self.voice.start()
                self.log("[语音] 已开启：说「干杯出来」唤醒")
            except Exception as e:
                self.log(f"[语音] 启动失败: {e}")
                return
        self.voice_on = not self.voice_on
        self.log(f"[语音] {'识别中' if self.voice_on else '已暂停'}")

    def _voice_cmd(self, cmd, params):
        self.log(f"[语音] 识别指令: {cmd} {params}")
        if cmd == "light":
            self.brain.set_light(params == "on")
        elif cmd == "mute":
            self.brain.set_mute(params == "on")
        elif cmd == "gear":
            self.brain.set_gear(params)
        elif cmd == "ebrk":
            self.brain.remote_ebrake()
        elif cmd == "strip":
            self.brain.set_strip(1 if params == "on" else 0)
        elif cmd == "horn":
            self.ceb.set_horn(True)

    # ---------- 状态 ----------
    def pump(self):
        """处理一帧：大脑收帧 + 小脑 tick，产出状态快照。"""
        f = self.brain.link.receive()
        if f:
            self.brain.handle_frame(*f)
        self.ceb.tick()
        self._emit_state()

    def _state(self):
        c = self.ceb
        return {
            "online": self.brain.cerebellum_online,
            "speed": c.speed,
            "throttle": c.throttle,
            "brake": c.brake,
            "gear": c.gear,
            "steer": c.steer,
            "light": c.light,
            "mute": c.mute,
            "strip": c.strip,
            "horn": c.horn,
            "ebrk": c.ebrk,
            "motor": c.motor,
        }

    def _emit_state(self):
        self.outbox.put(("state", self._state()))

    def log(self, text):
        self.outbox.put(("log", text))

    # ---------- 由事件循环调用 ----------
    async def drain(self):
        while not self.outbox.empty():
            kind, data = self.outbox.get_nowait()
            msg = json.dumps({"type": kind, "data": data}) if kind == "state" \
                else json.dumps({"type": kind, "text": data})
            for ws in list(self.clients):
                try:
                    await ws.send_str(msg)
                except Exception:
                    self.clients.discard(ws)


# ================= 全局核心 =================
core = TwinCore()


# ================= HTTP =================
async def index(request):
    return web.FileResponse(os.path.join(FRONTEND, "index.html"))


async def ws_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    core.clients.add(ws)
    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                try:
                    core.handle_command(json.loads(msg.data))
                except Exception as e:
                    print("命令处理错误:", e)
    finally:
        core.clients.discard(ws)
    return ws


async def pump_loop(app):
    while True:
        core.pump()
        await core.drain()
        await asyncio.sleep(0.02)


@web.middleware
async def no_cache(request, handler):
    """强制不缓存，确保浏览器刷新总是加载最新前端代码。"""
    resp = await handler(request)
    resp.headers["Cache-Control"] = "no-store"
    return resp


def build_app():
    app = web.Application(middlewares=[no_cache])
    app.router.add_get("/", index)
    app.router.add_get("/ws", ws_handler)
    app.router.add_static("/vendor", os.path.join(FRONTEND, "vendor"))
    app.router.add_static("/", FRONTEND)

    async def _start_pump(a):
        # aiohttp 会 await on_startup 回调；必须 async，且不能 return Task
        asyncio.create_task(pump_loop(a))

    app.on_startup.append(_start_pump)
    return app


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print("=" * 54)
    print("  🚗 干杯一号 · 数字孪生（大脑 + 小脑协同）")
    print(f"  打开浏览器:  http://localhost:{port}")
    print("  按 Ctrl+C 停止")
    print("=" * 54)
    web.run_app(build_app(), host="localhost", port=port)


if __name__ == "__main__":
    main()
