#!/usr/bin/env python3
"""干杯一号 · 双端数字孪生后端（大脑 + 小脑真实协同）

一个进程同时提供两个网页服务，共享同一套「大脑 + 小脑」：
  - http://localhost:8000   小车端（仪表盘区 + 控制区）
  - http://localhost:8001   家长端（GPS / 电量 / 对讲 / 视频，手机友好）

双端通过 WebSocket 看同一辆车的真实状态：
  /ws          小车端：发控制命令，收状态快照；收发对讲/视频帧
  /ws_parent   家长端：读状态 / 远程急刹；收发对讲/视频帧

真实信号链路：
  浏览器操作 → WS 命令 → 大脑决策 → 协议 V0.3 → 小脑执行 → 状态快照 → WS 推送双端

按真实硬件分层的模拟：
  - GPS：大脑层模拟（真实架构由树莓派读 4G/GPS 模块），随车速移动
  - 电量：小脑层模拟（真实架构由小脑 ADC 上报电池电压），按负载消耗

运行（在 software/raspberry_pi 目录）：
  .venv/Scripts/python.exe digital_twin/backend/twin_server.py [小车端口] [家长端口]
  浏览器打开 http://localhost:8000（小车端）、http://localhost:8001（家长端）
"""

import asyncio
import base64
import json
import math
import os
import queue
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

import aiohttp
from aiohttp import web

from car_brain.brain import Brain
from car_brain.serial_link import SerialLink
from car_brain.simulator import CerebellumSim, Pipe
from car_brain.protocol import commands as C
FRONTEND = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend")
)
KID_DIR = os.path.join(FRONTEND, "kid")
PARENT_DIR = os.path.join(FRONTEND, "parent")


class RealCerebellum:
    """真实小脑适配器：命令发给 Arduino，从大脑收到的 STAT 解析状态。

    接口对齐 CerebellumSim（set_throttle/press_button/...），让上层代码不变。
    真实模式下，大脑（Brain）直接连着 Arduino 串口，所有命令和状态都走同一条链路。

    ⚠️ 真实车辆：油门/刹车是小孩踩物理踏板 → Arduino 直读 A0/A1 → 本地驱动电机，
    不经过大脑（协议里没有 THROTTLE/STEER 命令）。网页的油门/刹车只是仿真，真实模式下
    set_throttle/set_brake 不发命令，状态从 STAT 上报读取。
    """

    def __init__(self, brain):
        self.brain = brain
        self.speed = 0.0
        self.throttle = 0
        self.brake = 0
        self.gear = 2
        self.light = False
        self.strip = False
        self.turn = " "
        self.horn = False
        self.ebrk = False
        self.motor = 0
        self.brake_light = 0
        self.voltage = 24.6
        self.current = 0.0
        self.temp = 32
        self.steer = 0.0

    # ---------- 命令（发给 Arduino，决策类） ----------
    def press_button(self, name):
        self.brain.link.send(C.BTN, f"{name},PRESS")

    def set_throttle(self, v):
        # 真实模式：油门来自物理踏板，不发送（只记录网页值供展示）
        self.throttle = max(0, min(100, int(v)))

    def set_brake(self, v):
        # 真实模式：刹车来自物理踏板，不发送
        self.brake = max(0, min(100, int(v)))

    def set_steer(self, v):
        # 真实模式：转向来自物理方向盘，不发送
        self.steer = max(-1.0, min(1.0, float(v)))

    def set_horn(self, on):
        self.horn = bool(on)
        self.brain.set_horn(on)

    def tick(self):
        """真实模式下无需 tick（Arduino 自己跑循环上报状态）。"""
        pass

    # ---------- 状态解析（从大脑收到的 STAT 帧） ----------
    def on_status(self, params):
        """解析 STAT:速度,油门,档位,电压,温度,电流"""
        try:
            parts = params.split(",")
            if len(parts) >= 6:
                self.speed = float(parts[0])
                self.throttle = int(float(parts[1]))
                self.gear = int(float(parts[2]))
                self.voltage = float(parts[3])
                self.temp = float(parts[4])
                self.current = float(parts[5])
        except (ValueError, IndexError):
            pass


class TwinCore:
    """大脑 + 小脑核心：双端共享的同一辆车。"""

    def __init__(self, real_serial: str | None = None):
        if real_serial:
            # ---- 真实硬件模式：大脑直接连 Arduino 串口 ----
            from car_brain.app import SerialPort
            port = SerialPort(real_serial, 115200)
            self.brain = Brain(SerialLink(port))
            self.ceb = RealCerebellum(self.brain)   # 真实小脑适配器
            print(f"[硬件] 真实模式：连接 Arduino {real_serial} @ 115200", flush=True)
        else:
            # ---- 仿真模式（默认）：内存管道连接大脑与小脑 ----
            self.bp, self.cp = Pipe(), Pipe()
            self.bp.peer, self.cp.peer = self.cp, self.bp
            self.ceb = CerebellumSim(self.cp)          # 小脑（虚拟）
            self.brain = Brain(SerialLink(self.bp))    # 大脑（真实决策）
        self.brain.on_event = self._on_brain_event
        self.brain.start()

        self.kid_clients = set()       # 小车端 WebSocket
        self.parent_clients = set()    # 家长端 WebSocket
        self.outbox = queue.Queue()    # ("state"|"log", data)，事件循环统一发送
        self.voice = None
        self.voice_on = False

        # 大脑层模拟：GPS（真实架构由 4G/GPS 模块读取）
        self.gps_lat = 39.9087
        self.gps_lng = 116.3975
        self.gps_heading = 0.0
        self.gps_sat = 11

    # ---------- 大脑事件 ----------
    def _on_brain_event(self, event, data):
        msgs = {
            "light": f"大灯 -> {'开' if data else '关'}",
            "mute": f"静音 -> {'开' if data else '关'}",
            "ebrk": "⚠️ 急刹触发！",
        }
        if event in msgs:
            self.log(msgs[event])
        if event == "status" and isinstance(self.ceb, RealCerebellum):
            # 真实模式：解析 Arduino 上报的 STAT 状态
            self.ceb.on_status(data)

    # ---------- 小车端命令入口 ----------
    def handle_kid_command(self, msg):
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
        elif t == "light":
            self.brain.set_light(bool(msg["value"]))
        elif t == "mute":
            self.brain.set_mute(bool(msg["value"]))
        elif t == "strip":
            self.brain.set_strip(1 if msg["value"] else 0)
        elif t == "horn":
            self.ceb.set_horn(bool(msg["value"]))
        elif t == "voice":
            self.toggle_voice()

    # ---------- 家长端命令入口 ----------
    def handle_parent_command(self, msg):
        t = msg.get("type")
        if t == "remote_ebrk":
            self.brain.remote_ebrake()
            self.log("📱 家长远程急刹！")

    # ---------- 语音识别（vosk，可选） ----------
    def toggle_voice(self):
        if self.voice is None:
            try:
                from car_brain.voice import VoiceController

                self.voice = VoiceController()
                self.voice.on_command = self._voice_cmd
                self.voice.on_status = lambda t: self.log(f"[语音] {t}")
                self.voice.start()
                # 开启即常开：不用唤醒词，直接说指令即可，且每条指令后持续有效
                self.voice.awake = True
                self.voice._awake_until = time.time() + 3600
                self.voice.always_awake = True
                self.log("[语音] 已开启：请直接说指令（如「打开大灯」「三档」）")
                print("[语音] 已开启：请直接说指令（如「打开大灯」「三档」）", flush=True)
            except Exception as e:
                self.log(f"[语音] 启动失败: {e}")
                print(f"[语音] 启动失败: {e}", flush=True)
                return
        self.voice_on = not self.voice_on
        self.log(f"[语音] {'识别中' if self.voice_on else '已暂停'}")
        print(f"[语音] {'识别中' if self.voice_on else '已暂停'}", flush=True)

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
        # 真实模式下 Arduino 自己跑循环上报，无需 tick
        if isinstance(self.ceb, CerebellumSim):
            self.ceb.tick()
        self._update_gps()
        self._emit_state()

    def _update_gps(self):
        """模拟 GPS：速度越大移动越快，行驶中缓慢右转形成轨迹。"""
        speed = self.ceb.speed
        dt = 0.02
        dist = speed * dt  # 米
        if speed > 0.1:
            self.gps_heading = (self.gps_heading + 0.9 * (speed / 25.0)) % 360.0
        m_per_deg = 111320.0
        self.gps_lat += dist * math.cos(math.radians(self.gps_heading)) / m_per_deg
        self.gps_lng += dist * math.sin(math.radians(self.gps_heading)) / (
            m_per_deg * math.cos(math.radians(self.gps_lat))
        )

    def _battery_pct(self):
        # 24.6V 满电 -> 100%，22.2V 空电 -> 0%
        v = self.ceb.voltage
        pct = (v - 22.2) / (24.6 - 22.2) * 100.0
        return max(0.0, min(100.0, pct))

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
            "turn": c.turn,
            "horn": c.horn,
            "ebrk": c.ebrk,
            "motor": c.motor,
            "brake_light": c.brake_light,
            "voltage": c.voltage,
            "current": c.current,
            "temp": c.temp,
            "battery_pct": self._battery_pct(),
            "gps": {
                "lat": self.gps_lat,
                "lng": self.gps_lng,
                "sat": self.gps_sat,
                "heading": self.gps_heading,
            },
        }

    def _emit_state(self):
        self.outbox.put(("state", self._state()))

    def log(self, text):
        self.outbox.put(("log", text))

    # ---------- 对讲 / 视频转发（双端互转） ----------
    async def _relay(self, target_set, msg):
        for ws in list(target_set):
            try:
                await ws.send_str(json.dumps(msg))
            except Exception:
                target_set.discard(ws)

    async def relay_to_parents(self, msg):
        await self._relay(self.parent_clients, msg)

    async def relay_to_kids(self, msg):
        await self._relay(self.kid_clients, msg)

    async def broadcast_to_kids(self, text: str):
        """把小智桥接的回复/日志推给小车端（text 已是 JSON 字符串）。"""
        for ws in list(self.kid_clients):
            try:
                await ws.send_str(text)
            except Exception:
                self.kid_clients.discard(ws)

    # ---------- 事件循环统一发送 ----------
    async def drain(self):
        while not self.outbox.empty():
            kind, data = self.outbox.get_nowait()
            msg = json.dumps({"type": kind, "data": data}) if kind == "state" \
                else json.dumps({"type": kind, "text": data})
            for ws in list(self.kid_clients):
                try:
                    await ws.send_str(msg)
                except Exception:
                    self.kid_clients.discard(ws)
            for ws in list(self.parent_clients):
                try:
                    await ws.send_str(msg)
                except Exception:
                    self.parent_clients.discard(ws)


# ================= 全局核心（双端共享同一辆车） =================
core = TwinCore()


# ================= 小智桥接客户端（转发给独立 xiaozhi_bridge 进程） =================
class XiaozhiBridgeClient:
    """连接本地 xiaozhi_bridge（8010），把小车端的 xiaozhi 消息转发给它，
    并把小智回复推回小车端。"""

    BRIDGE_URL = "ws://127.0.0.1:8010/xiaozhi"

    def __init__(self):
        self.ws = None
        self._connected = False

    async def connect(self):
        """连桥接，失败自动重连。"""
        while True:
            try:
                async with aiohttp.ClientSession() as sess:
                    async with sess.ws_connect(self.BRIDGE_URL) as ws:
                        self.ws = ws
                        self._connected = True
                        print("[小智] 桥接已连接", flush=True)
                        async for msg in ws:
                            if msg.type == web.WSMsgType.TEXT:
                                # 把桥接的回复/日志推给小车端
                                data = msg.json() if isinstance(msg.json(), dict) else {}
                                await core.broadcast_to_kids(json.dumps(data))
            except Exception as e:
                print(f"[小智] 桥接连接断开: {e}", flush=True)
            self._connected = False
            await asyncio.sleep(3)

    async def send(self, msg: dict):
        if self.ws and not self.ws.closed:
            try:
                await self.ws.send_str(json.dumps(msg))
                return True
            except Exception:
                pass
        print("[小智] 桥接未连接，丢弃消息", flush=True)
        return False


xiaozhi_bridge = XiaozhiBridgeClient()


# ================= WebSocket 处理器 =================
async def _ws_loop(ws, clients, command_handler, relay_to_peer):
    clients.add(ws)
    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                except Exception:
                    continue
                t = data.get("type")
                if t == "xiaozhi":
                    # 小智对话：转发给桥接进程（不进大脑/小脑）
                    await xiaozhi_bridge.send(data)
                elif t in ("audio", "video", "call", "hangup"):
                    # 多媒体消息：转发给对端
                    data["from"] = data.get("from", "kid" if clients is core.kid_clients else "parent")
                    if t in ("call", "hangup"):
                        print(f"[媒体] {data['from']} -> {t}", flush=True)
                    await relay_to_peer(data)
                else:
                    command_handler(data)
            elif msg.type == web.WSMsgType.ERROR:
                break
    finally:
        clients.discard(ws)
    return ws


async def ws_kid_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    return await _ws_loop(ws, core.kid_clients, core.handle_kid_command,
                          core.relay_to_parents)


async def ws_parent_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    return await _ws_loop(ws, core.parent_clients, core.handle_parent_command,
                          core.relay_to_kids)


# ================= 状态泵（只跑一次，服务双端） =================
async def pump_loop():
    while True:
        core.pump()
        await core.drain()
        await asyncio.sleep(0.02)


# ================= HTTP 服务器构造 =================
@web.middleware
async def no_cache(request, handler):
    """强制不缓存，确保浏览器刷新总是加载最新前端代码。"""
    resp = await handler(request)
    resp.headers["Cache-Control"] = "no-store"
    return resp


# ================= 本地控制 API（干杯助手 MCP 工具 → 大脑） =================
async def control_handler(request):
    """接收干杯助手 MCP 工具的控制命令，调用大脑执行。
    body: {"action": "light"|"strip"|"mute"|"gear"|"horn"|"ebrk", "value": ...}
    """
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "bad json"}, status=400)
    action = body.get("action")
    value = body.get("value")
    brain = core.brain
    if action == "light":
        brain.set_light(bool(value))
    elif action == "strip":
        brain.set_strip(1 if value else 0)
    elif action == "mute":
        brain.set_mute(bool(value))
    elif action == "gear":
        brain.set_gear(int(value))
    elif action == "horn":
        brain.set_horn(bool(value))
    elif action == "ebrk":
        brain.remote_ebrake()
    else:
        return web.json_response({"ok": False, "error": f"unknown action {action}"}, status=400)
    core.log(f"🎙 干杯助手控制: {action}={value}")
    return web.json_response({"ok": True})


def build_kid_app():
    app = web.Application(middlewares=[no_cache])
    app.router.add_get("/ws", ws_kid_handler)
    app.router.add_get("/", lambda r: web.FileResponse(os.path.join(KID_DIR, "index.html")))
    app.router.add_static("/static", KID_DIR)
    # 本地控制 API（供干杯助手 MCP 工具调用大脑）
    app.router.add_post("/api/control", control_handler)
    return app


def build_parent_app():
    app = web.Application(middlewares=[no_cache])
    app.router.add_get("/ws", ws_parent_handler)
    app.router.add_get("/", lambda r: web.FileResponse(os.path.join(PARENT_DIR, "index.html")))
    app.router.add_static("/static", PARENT_DIR)
    return app


async def main():
    global core
    # 解析参数：--real-serial <串口> 切换真实硬件模式（默认仿真）
    real_serial = None
    if "--real-serial" in sys.argv:
        idx = sys.argv.index("--real-serial")
        if idx + 1 < len(sys.argv):
            real_serial = sys.argv[idx + 1]
        else:
            print("用法：--real-serial <串口>，如 --real-serial /dev/ttyACM0")
            sys.exit(1)
    # 端口参数（去掉 --real-serial 相关）
    args = [a for a in sys.argv[1:] if not a.startswith("--real-serial")]
    kid_port = int(args[0]) if len(args) > 0 and args[0].isdigit() else 8000
    parent_port = int(args[1]) if len(args) > 1 and args[1].isdigit() else 8001

    if real_serial:
        # 重新构建 core（真实硬件模式）
        core = TwinCore(real_serial=real_serial)
        print("=" * 50)
        print(f"  🚗 干杯一号 · 真实硬件模式")
        print(f"  小脑: Arduino {real_serial} @ 115200")
        print("=" * 50)

    # 状态泵只启动一次（双端共享核心）
    asyncio.create_task(pump_loop())

    # 小智桥接连接（独立进程 xiaozhi_bridge 已启动于 8010）
    asyncio.create_task(xiaozhi_bridge.connect())

    kid_runner = web.AppRunner(build_kid_app())
    await kid_runner.setup()
    kid_site = web.TCPSite(kid_runner, "0.0.0.0", kid_port)
    await kid_site.start()

    parent_runner = web.AppRunner(build_parent_app())
    await parent_runner.setup()
    parent_site = web.TCPSite(parent_runner, "0.0.0.0", parent_port)
    await parent_site.start()

    print("=" * 58)
    print("  🚗 干杯一号 · 双端数字孪生（大脑 + 小脑真实协同）")
    print(f"  小车端: http://localhost:{kid_port}    (仪表盘 + 控制区)")
    print(f"  家长端: http://localhost:{parent_port}  (GPS/电量/对讲/视频)")
    print("  手机访问家长端：用局域网 IP（同一 Wi-Fi），如 http://192.168.x.x:8001")
    print("  按 Ctrl+C 停止")
    print("=" * 58)

    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await kid_runner.cleanup()
        await parent_runner.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
