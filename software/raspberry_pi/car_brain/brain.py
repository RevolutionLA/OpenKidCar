"""大脑状态机（Brain）。

职责：
  - 维护执行状态视图（档位 / 灯光 / 静音 / 就座 / 急刹 / 小脑在线）
  - 处理小脑上行帧：READY / PONG / ACK / BTN / SEAT / EBRK / STAT
  - 将按钮事件转换为具体命令下发
  - 心跳保活 + 离线检测
  - 供上层（语音 / APP / 桌面模拟）调用的主动命令接口

事件通过 on_event 回调对外暴露（测试可注入），事件名：
  ready / ack / button / seat / ebrk / status / light / mute / offline
"""

import logging
import threading
import time

from .protocol import commands as C
from .serial_link import SerialLink

log = logging.getLogger("brain")


class Brain:
    def __init__(self, link: SerialLink, heartbeat_interval: float = 1.0):
        self.link = link
        self.heartbeat_interval = heartbeat_interval

        # ---- 大脑维护的状态视图（以大脑决策为准）----
        self.gear = 2
        self.light = False
        self.strip = False
        self.mute = False
        self.seat = False
        self.ebrk = False
        self.cerebellum_online = False

        # 待 ACK 确认的命令（简化：记最近一条，收到 ACK 即清除）
        self._pending_cmd = None

        # 事件回调：on_event(事件名, 数据)
        self.on_event = None

        self._running = False
        self._heartbeat_thread = None

    # ================= 内部 =================
    def _emit(self, event: str, data=None):
        if self.on_event:
            self.on_event(event, data)

    def _send(self, cmd: str, params: str | None = None):
        """发送命令；非心跳命令记为待确认。"""
        self.link.send(cmd, params)
        if cmd != C.PING:
            self._pending_cmd = cmd

    # ================= 处理上行帧 =================
    def handle_frame(self, cmd: str, params: str):
        if cmd == C.READY:
            self.cerebellum_online = True
            self._emit("ready", params)
            # 握手：向小脑重新同步当前状态
            self._send(C.GEAR, str(self.gear))
            self._send(C.LIGHT, "ON" if self.light else "OFF")
            self._send(C.MUTE, "ON" if self.mute else "OFF")
        elif cmd == C.PONG:
            self.cerebellum_online = True
        elif cmd == C.ACK:
            self._pending_cmd = None
            if params != "OK":
                log.warning("小脑拒绝命令: %s", params)
            self._emit("ack", params)
        elif cmd == C.BTN:
            self._handle_btn(params)
        elif cmd == C.SEAT:
            self.seat = (params == "ON")
            self._emit("seat", self.seat)
        elif cmd == C.EBRK:
            # 小脑本地急刹触发（硬件按钮直连），大脑同步状态
            self.ebrk = True
            self._emit("ebrk")
        elif cmd == C.STAT:
            self._emit("status", params)
        else:
            log.debug("未处理帧: %s %s", cmd, params)

    def _handle_btn(self, params: str):
        name, _, action = params.partition(",")
        if action != "PRESS":
            return
        if name == C.LIGHT_BTN:
            self.light = not self.light
            self._send(C.LIGHT, "ON" if self.light else "OFF")
            self._emit("light", self.light)
        elif name == C.MUTE_BTN:
            self.mute = not self.mute
            self._send(C.MUTE, "ON" if self.mute else "OFF")
            self._emit("mute", self.mute)
        elif name == C.EBRK_BTN:
            # 急刹 toggle：按下触发，再按解除
            self.ebrk = not self.ebrk
            self._send(C.EBRK, "ON" if self.ebrk else "OFF")
            self._emit("ebrk", self.ebrk)
        elif name == C.STRIP_BTN:
            # 灯带：大脑决策切换，下发 STRIP 命令给小脑执行
            self.strip = not self.strip
            self._send(C.STRIP, f"{1 if self.strip else 0},FFFFFF,100")
            self._emit("strip", self.strip)
        elif name == C.HORN_BTN:
            self._emit("horn_btn")
        elif name == C.TALK_BTN:
            self._emit("talk_btn")
        else:
            self._emit("button", params)

    # ================= 主动命令（供上层调用）=================
    def set_gear(self, gear: int):
        if -1 <= gear <= 4:   # -1 = R 倒车，1-4 = 前进档
            self.gear = gear
            self._send(C.GEAR, str(gear))

    def set_light(self, on: bool):
        self.light = on
        self._send(C.LIGHT, "ON" if on else "OFF")

    def set_mute(self, on: bool):
        self.mute = on
        self._send(C.MUTE, "ON" if on else "OFF")

    def remote_ebrake(self):
        """APP 远程急刹（最高优先级）。"""
        self.ebrk = True
        self._send(C.EBRK, "ON")

    def release_ebrake(self):
        """APP 解除急刹（仅家长端授权）。"""
        self.ebrk = False
        self._send(C.EBRK, "OFF")

    def set_strip(self, mode: int, color: int = 0xFFFFFF, brightness: int = 100):
        """RGB 灯带：mode(0 关/1 常亮/2 呼吸...), color(0xRRGGBB), brightness(0-255)。"""
        self._send(C.STRIP, f"{mode},{color:06X},{brightness}")

    def set_turn(self, direction: str):
        """转向灯：'L' / 'R' / 'off'。"""
        d = direction.upper() if direction in ("L", "R") else "OFF"
        self._send(C.TURN, d)

    def set_steer(self, angle: int):
        """转向：0-180 角度（90=直行）。"""
        a = max(0, min(180, int(angle)))
        self._send(C.STEER, str(a))

    def set_horn(self, on: bool):
        """鸣笛：True 开始，False 停止。"""
        self._send(C.HORN, "ON" if on else "OFF")

    # ================= 心跳 =================
    def start(self):
        self._running = True
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop, daemon=True
        )
        self._heartbeat_thread.start()

    def stop(self):
        self._running = False
        if self._heartbeat_thread:
            self._heartbeat_thread.join(timeout=2)

    def _heartbeat_loop(self):
        missed = 0
        while self._running:
            time.sleep(self.heartbeat_interval)
            self.link.send(C.PING)
            if not self.cerebellum_online:
                missed += 1
                if missed >= 3:
                    self._emit("offline")
            else:
                missed = 0
