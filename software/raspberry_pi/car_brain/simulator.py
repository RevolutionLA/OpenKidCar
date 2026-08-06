"""干杯一号 · 桌面模拟器（pygame 可视化驾驶舱）

三列布局：
  左：圆形速度表 + 油门/刹车踏板
  中：中控台（大灯/静音/灯带/喇叭/急刹/档位/语音）+ 电机能量条 + 灯光 + 数据
  右：摄像头（行车记录/自拍）+ 对讲机 + 事件日志

内置"小脑引擎"（CerebellumSim）复用协议与 Brain 类，内存管道连接。
可选：真实语音控制（--voice）、引擎轰鸣音效（自动）。

运行：
  python -m car_brain.simulator [--voice]
"""

import argparse
import math
import os
import threading
import time

import pygame

from .brain import Brain
from .protocol import commands as C
from .serial_link import SerialLink
from .sim_audio import EngineSound
from .sim_camera import CameraView
from .tts import TTS

# ============ 字体 ============
_FONT_CANDIDATES = [
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/msyhbd.ttc",
]


def _load_font(size):
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            return pygame.font.Font(path, size)
    return pygame.font.Font(None, size)


# ============ 配色 ============
BG = (13, 17, 23)
PANEL = (20, 26, 34)
PANEL_LINE = (42, 53, 68)
TEXT = (232, 238, 244)
TEXT_DIM = (140, 156, 173)
ACCENT = (56, 189, 248)
CYAN = (34, 211, 238)
GREEN = (52, 211, 153)
YELLOW = (251, 191, 36)
RED = (248, 113, 113)
GRID = (26, 33, 44)

W, H = 1100, 680

# ============ 面板布局（避免遮挡） ============
SPEED_PANEL = pygame.Rect(30, 90, 310, 290)
PEDAL_PANEL = pygame.Rect(30, 390, 310, 250)
CTRL_PANEL = pygame.Rect(360, 40, 330, 300)
ENERGY_RECT = pygame.Rect(360, 350, 330, 90)
LIGHT_RECT = pygame.Rect(360, 450, 330, 60)
DATA_RECT = pygame.Rect(360, 520, 330, 110)
CAM_RECT = pygame.Rect(710, 40, 360, 220)
TALK_RECT = pygame.Rect(710, 270, 360, 150)
LOG_RECT = pygame.Rect(710, 430, 360, 200)


# ============ 内存管道 ============
class Pipe:
    def __init__(self, peer=None):
        self.peer = peer
        self.buf = b""
        self.lock = threading.Lock()

    def write(self, data):
        with self.peer.lock:
            self.peer.buf += data

    def read(self, size, timeout=0.05):
        with self.lock:
            if self.buf:
                chunk, self.buf = self.buf[:size], self.buf[size:]
                return chunk
        return b""


# ============ 小脑引擎 ============
GEAR_SPEED_MAX = {1: 10, 2: 15, 3: 20, 4: 25}


class CerebellumSim:
    def __init__(self, pipe):
        self.link = SerialLink(pipe)
        self.throttle = 0
        self.brake = 0
        self.gear = 2
        self.light = False
        self.strip = False
        self.strip_mode = 0
        self.strip_color = 0xFFFFFF
        self.mute = False
        self.turn = " "
        self.horn = False
        self.ebrk = False
        self.brake_light = 0
        self.motor = 0
        self.speed = 0
        self.voltage = 24.6
        self.temp = 32
        self.current = 0.0
        self.steer = 0.0          # 转向 -1..1（方向盘传感）
        self._ready = False

    def press_button(self, name):
        self.link.send(C.BTN, f"{name},PRESS")

    def set_throttle(self, v):
        self.throttle = max(0, min(100, int(v)))

    def set_brake(self, v):
        self.brake = max(0, min(100, int(v)))

    def set_steer(self, v):
        self.steer = max(-1.0, min(1.0, float(v)))

    def set_horn(self, on):
        self.horn = bool(on)

    def tick(self):
        if not self._ready:
            self.link.send(C.READY, "V0.3")
            self._ready = True
        frame = self.link.receive()
        if frame:
            self._handle(frame)
        if int(time.time() * 10) != getattr(self, "_t10", -1):
            self._t10 = int(time.time() * 10)
            self._report()

    def _handle(self, frame):
        cmd, params = frame
        if cmd == C.PING:
            self.link.send(C.PONG)
        elif cmd == C.LIGHT:
            self.light = (params == "ON")
            self._ack()
        elif cmd == C.STRIP:
            try:
                parts = params.split(",")
                self.strip_mode = int(parts[0])
                if len(parts) > 1:
                    self.strip_color = int(parts[1], 16)
                self.strip = self.strip_mode > 0
            except ValueError:
                pass
            self._ack()
        elif cmd == C.MUTE:
            self.mute = (params == "ON")
            self._ack()
        elif cmd == C.GEAR:
            self.gear = max(1, min(4, int(params)))
            self._ack()
        elif cmd == C.TURN:
            self.turn = params if params in ("L", "R", "OFF") else " "
            self._ack()
        elif cmd == C.HORN:
            self.horn = (params == "ON")
            self._ack()
        elif cmd == C.BRAKE:
            self.ebrk = False
            self._ack()
        elif cmd == C.EBRK:
            self.ebrk = (params == "ON")
            self.brake = 100 if self.ebrk else 0
            self._ack()

    def _ack(self):
        self.link.send(C.ACK, "OK")

    def _report(self):
        # 速度物理（积分式）：油门加速逼近目标，刹车/急刹减速
        max_spd = GEAR_SPEED_MAX.get(self.gear, 10)
        if self.ebrk or self.brake > 10:
            # 刹车越深，减速越快；急刹立即停
            decel = 60 if self.ebrk else self.brake * 0.25
            self.speed = max(0, self.speed - decel)
        else:
            target = self.throttle * max_spd / 100
            self.speed += (target - self.speed) * 0.12   # 平滑逼近目标速度
        self.motor = 0 if (self.ebrk or self.brake > 10) else self.throttle
        self.brake_light = 255 if (self.ebrk or self.brake > 10) else 0
        self.current = self.motor * 0.05
        self.link.send(C.STAT, f"{self.speed},{self.throttle},{self.gear},"
                                f"{self.voltage:.1f},{self.temp},{self.current:.1f}")


# ============ 绘制工具 ============
def glow(surface, center, radius, color, alpha=90):
    s = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
    for r in range(radius, 0, -3):
        a = int(alpha * (1 - r / radius))
        pygame.draw.circle(s, (*color, a), (radius, radius), r)
    surface.blit(s, (center[0] - radius, center[1] - radius))


def hgrad(surface, rect, c1, c2):
    for x in range(rect.w):
        t = x / max(1, rect.w - 1)
        c = tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))
        pygame.draw.line(surface, c, (rect.x + x, rect.y), (rect.x + x, rect.y + rect.h - 1))


def panel(surface, rect, title=None, font=None):
    pygame.draw.rect(surface, PANEL, rect, border_radius=14)
    pygame.draw.rect(surface, PANEL_LINE, rect, 1, border_radius=14)
    if title and font:
        surface.blit(font.render(title, True, ACCENT), (rect.x + 14, rect.y + 10))


# ============ 控件 ============
class Button:
    def __init__(self, rect, label, on_click=None, on_release=None,
                 color=PANEL, text_color=TEXT):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.on_click = on_click
        self.on_release = on_release
        self.color = color
        self.text_color = text_color
        self.hover = False
        self.pressed = False

    def draw(self, surface, font):
        c = self.color
        if self.pressed:
            c = tuple(min(255, x + 40) for x in c)
        elif self.hover:
            c = tuple(min(255, x + 20) for x in c)
        pygame.draw.rect(surface, c, self.rect, border_radius=10)
        pygame.draw.rect(surface, PANEL_LINE, self.rect, 1, border_radius=10)
        t = font.render(self.label, True, self.text_color)
        surface.blit(t, t.get_rect(center=self.rect.center))

    def handle(self, event):
        if event.type == pygame.MOUSEMOTION:
            self.hover = self.rect.collidepoint(event.pos)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self.pressed = True
                if self.on_click:
                    self.on_click()
                return True
        elif event.type == pygame.MOUSEBUTTONUP:
            was = self.pressed
            self.pressed = False
            if was and self.on_release:
                self.on_release()
        return False


class Pedal:
    def __init__(self, rect, label, color, on_change):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.color = color
        self.on_change = on_change
        self.value = 0
        self._drag = False

    def draw(self, surface, font, small):
        base = self.rect.inflate(24, 24)
        pygame.draw.rect(surface, PANEL, base, border_radius=16)
        pygame.draw.rect(surface, PANEL_LINE, base, 1, border_radius=16)
        fh = int(self.rect.h * self.value / 100)
        fill = pygame.Rect(self.rect.x, self.rect.bottom - fh, self.rect.w, fh)
        if fh > 0:
            hgrad(surface, fill, tuple(int(c * 0.6) for c in self.color), self.color)
            glow(surface, fill.center, 16, self.color, 40)
        pygame.draw.rect(surface, PANEL_LINE, self.rect, 2, border_radius=10)
        pygame.draw.ellipse(surface, PANEL, self.rect.inflate(-10, -8))
        txt = font.render(self.label, True, self.color)
        surface.blit(txt, txt.get_rect(center=(self.rect.centerx, self.rect.centery - 6)))
        v = small.render(f"{self.value}%", True, TEXT)
        surface.blit(v, v.get_rect(center=(self.rect.centerx, self.rect.centery + 18)))

    def handle(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.rect.collidepoint(event.pos):
            self._drag = True
        elif event.type == pygame.MOUSEBUTTONUP:
            self._drag = False
        elif event.type == pygame.MOUSEMOTION and self._drag:
            self.value = max(0, min(100, int((self.rect.bottom - event.pos[1]) / self.rect.h * 100)))
            self.on_change(self.value)
        return self._drag


# ============ 模拟器 ============
class Simulator:
    def __init__(self, voice=False):
        pygame.init()
        self.screen = pygame.display.set_mode((W, H))
        pygame.display.set_caption("干杯一号 · 桌面模拟器")
        self.clock = pygame.time.Clock()
        self.font = _load_font(22)
        self.small = _load_font(17)
        self.tiny = _load_font(15)
        self.big = _load_font(50)
        self.title_font = _load_font(26)

        # 大脑 + 小脑引擎
        self.bp, self.cp = Pipe(), Pipe()
        self.bp.peer, self.cp.peer = self.cp, self.bp
        self.ceb = CerebellumSim(self.cp)
        self.brain = Brain(SerialLink(self.bp))
        self.brain.on_event = self._on_brain_event
        self.brain.start()

        # 引擎轰鸣（自动启动，失败则静音模式）
        self.engine = EngineSound()
        self.engine.start()

        # TTS（对讲语音）
        self.tts = TTS()

        # 摄像头
        self.camera = CameraView(CAM_RECT, self.small)

        self.logs = []
        self.talk_status = "待机"
        self.talk_active = False
        self._make_widgets()

        self.voice = None
        if voice:
            self._setup_voice()

    # ---------- 控件 ----------
    def _make_widgets(self):
        self.btns = {}
        # 中控台：2x2
        defs = [
            ("大灯", "LIGHT_BTN", PANEL),
            ("静音", "MUTE_BTN", PANEL),
            ("灯带", "STRIP_BTN", PANEL),
            ("喇叭", "HORN_BTN", PANEL),
        ]
        bw, bh, gap = 130, 46, 12
        bx, by = 375, 56
        for i, (label, name, color) in enumerate(defs):
            x = bx + (i % 2) * (bw + gap)
            y = by + (i // 2) * (bh + gap)
            self.btns[name] = Button((x, y, bw, bh), label,
                                     lambda n=name: self.ceb.press_button(n), color=color)

        # 急刹
        self.ebrk_btn = Button((bx, by + (bh + gap) * 2 + 4, bw * 2 + gap, 42),
                               "急 刹", lambda: self.ceb.press_button("EBRK_BTN"), color=RED)
        # 档位 + 语音（一行）
        gy = by + (bh + gap) * 2 + 4 + 42 + 8
        self.gear_btns = []
        for g in range(1, 5):
            x = bx + (g - 1) * 52
            self.gear_btns.append(Button((x, gy, 46, 40), f"{g}",
                                         lambda gg=g: self.brain.set_gear(gg)))
        self.voice_btn = Button((bx + 4 * 52 + 4, gy, 110, 40),
                                "语音:开灯", self._simulate_voice, color=(40, 66, 58))

        # 踏板
        self.throttle_pedal = Pedal((70, 470, 110, 140), "油门", GREEN,
                                    lambda v: (self.ceb.set_throttle(v), self.engine.set_throttle(v)))
        self.brake_pedal = Pedal((210, 470, 110, 140), "刹车", YELLOW, self.ceb.set_brake)

        # 摄像头翻转
        self.cam_btn = Button((CAM_RECT.right - 130, CAM_RECT.y + 6, 118, 30),
                              "翻转自拍", self.camera.toggle)

        # 对讲
        self.talk_btn = Button((724, 104, 160, 36), "按住说话(孩子)",
                               self._talk_press, self._talk_release, (40, 80, 66))
        self.parent_btn = Button((892, 104, 150, 36), "家长发语音",
                                 self._parent_msg, color=(66, 56, 92))

    # ---------- 语音 ----------
    def _setup_voice(self):
        try:
            from .voice import VoiceController
            self.voice = VoiceController()

            def on_cmd(cmd, params):
                self._log(f"[语音] {cmd} {params}")
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
                    self.brain.set_horn(params == "on")
                elif cmd == "turn":
                    self.brain.set_turn(params)

            self.voice.on_command = on_cmd
            self.voice.on_status = lambda t: self._log(f"[语音] {t}")
            self.voice.start()
            self._log("[语音] 已开启：说「干杯出来」唤醒")
        except Exception as e:
            self._log(f"[语音] 启动失败: {e}")

    def _simulate_voice(self):
        self._log("[语音] 识别: 干杯出来开灯")
        self.brain.set_light(True)

    # ---------- 对讲 ----------
    def _talk_press(self):
        self.talk_active = True
        self.talk_status = "对讲中…"
        self.tts.speak("爸爸，我在这里！")
        self._log("孩子: 按下对讲，语音发送中…")

    def _talk_release(self):
        self.talk_active = False
        self.talk_status = "已发送给家长"
        self._log("对讲完成 → 已发送")

    def _parent_msg(self):
        self.talk_status = "家长发来语音"
        self.tts.speak("宝宝，注意安全，爸爸在看着你。")
        self._log("家长: 发来一条语音")

    # ---------- 大脑事件 ----------
    def _on_brain_event(self, event, data):
        if event == "light":
            self._log(f"大灯 -> {'开' if data else '关'}")
        elif event == "mute":
            self.engine.set_mute(data)
            self._log(f"静音 -> {'开' if data else '关'}")
        elif event == "ebrk":
            self._log("[警告] 急刹触发！")

    def _log(self, msg):
        self.logs.append(msg)
        if len(self.logs) > 6:
            self.logs.pop(0)

    # ---------- 绘制 ----------
    def _bg(self):
        self.screen.fill(BG)
        for x in range(0, W, 48):
            pygame.draw.line(self.screen, GRID, (x, 0), (x, H))
        for y in range(0, H, 48):
            pygame.draw.line(self.screen, GRID, (0, y), (W, y))

    def _title(self):
        t = self.title_font.render("干杯一号 · 桌面模拟器", True, TEXT)
        self.screen.blit(t, (30, 24))
        self.screen.blit(self.small.render("GANBEI NO.1", True, TEXT_DIM), (34, 56))
        status = self.small.render(
            "大脑 ● 在线" if self.brain.cerebellum_online else "大脑 ● 连接中",
            True, GREEN if self.brain.cerebellum_online else YELLOW)
        self.screen.blit(status, (W - 230, 34))

    def _speedometer(self, cx, cy, r):
        rect = pygame.Rect(cx - r, cy - r, r * 2, r * 2)
        pygame.draw.circle(self.screen, PANEL, (cx, cy), r)
        pygame.draw.circle(self.screen, PANEL_LINE, (cx, cy), r, 2)
        glow(self.screen, (cx, cy), r, CYAN, 26 if self.ceb.speed == 0 else 70)

        a0, a1 = math.radians(-225), math.radians(45)
        speed_frac = min(1.0, self.ceb.speed / 25.0)
        pygame.draw.arc(self.screen, PANEL_LINE, rect.inflate(-14, -14), a0, a1, 8)
        if speed_frac > 0:
            c = GREEN if speed_frac < 0.5 else (CYAN if speed_frac < 0.85 else RED)
            pygame.draw.arc(self.screen, c, rect.inflate(-14, -14), a0, a0 + (a1 - a0) * speed_frac, 8)
        for i in range(9):
            ang = a0 + (a1 - a0) * i / 8
            px, py = cx + (r - 22) * math.cos(ang), cy + (r - 22) * math.sin(ang)
            tx, ty = cx + (r - 34) * math.cos(ang), cy + (r - 34) * math.sin(ang)
            pygame.draw.line(self.screen, TEXT_DIM, (px, py), (tx, ty), 2)
        if speed_frac > 0:
            ang = a0 + (a1 - a0) * speed_frac
            ex, ey = cx + (r - 38) * math.cos(ang), cy + (r - 38) * math.sin(ang)
            pygame.draw.line(self.screen, RED, (cx, cy), (ex, ey), 4)
            pygame.draw.circle(self.screen, RED, (cx, cy), 6)
        sv = self.big.render(str(self.ceb.speed), True, TEXT)
        self.screen.blit(sv, sv.get_rect(center=(cx, cy + 4)))
        self.screen.blit(self.small.render("km/h", True, TEXT_DIM),
                         self.small.render("km/h", True, TEXT_DIM).get_rect(center=(cx, cy + 40)))
        self.screen.blit(self.small.render(f"档位 {self.ceb.gear}", True, ACCENT),
                         self.small.render(f"档位 {self.ceb.gear}", True, ACCENT).get_rect(center=(cx, cy + 64)))

    def _energy_bar(self, rect):
        panel(self.screen, rect)
        self.screen.blit(self.small.render("电机输出", True, TEXT_DIM), (rect.x + 14, rect.y + 10))
        bar = pygame.Rect(rect.x + 14, rect.y + 36, rect.w - 28, 22)
        pygame.draw.rect(self.screen, (30, 38, 48), bar, border_radius=11)
        pct = self.ceb.motor / 100
        if pct > 0:
            fill = pygame.Rect(bar.x, bar.y, int(bar.w * pct), bar.h)
            hgrad(self.screen, fill, (28, 120, 120), GREEN if pct < 0.7 else YELLOW)
            pygame.draw.rect(self.screen, GREEN, fill, border_radius=11)
            glow(self.screen, (fill.right, bar.centery), 24, GREEN, 50)
        pv = self.font.render(f"{self.ceb.motor}%", True, TEXT)
        self.screen.blit(pv, pv.get_rect(center=(bar.centerx, bar.centery)))

    def _lights_row(self, rect):
        panel(self.screen, rect)
        items = [
            ("大灯", GREEN, self.ceb.light),
            ("灯带", CYAN, self.ceb.strip),
            ("转向", ACCENT, self.ceb.turn in ("L", "R")),
            ("刹车灯", RED, self.ceb.brake_light),
        ]
        for i, (name, color, on) in enumerate(items):
            cx = rect.x + 38 + i * 76
            cy = rect.y + 32
            if on:
                glow(self.screen, (cx, cy), 14, color, 70)
            pygame.draw.circle(self.screen, color if on else (45, 52, 64), (cx, cy), 6)
            self.screen.blit(self.tiny.render(name, True, TEXT_DIM), (cx - 16, cy + 14))

    def _data(self, rect):
        panel(self.screen, rect, "车辆数据")
        cells = [
            (f"{self.ceb.voltage:.1f}V", "电压"),
            (f"{self.ceb.temp}℃", "温度"),
            (f"{self.ceb.current:.1f}A", "电流"),
            ("行驶中" if self.ceb.speed > 0 else "静止", "状态"),
        ]
        for i, (val, name) in enumerate(cells):
            x = rect.x + 24 + (i % 2) * 130
            y = rect.y + 38 + (i // 2) * 40
            self.screen.blit(self.font.render(val, True, TEXT), (x, y))
            self.screen.blit(self.tiny.render(name, True, TEXT_DIM), (x + 60, y + 6))

    def _talk(self, rect):
        panel(self.screen, rect, "对讲机（家长 ↔ 孩子）")
        st = self.small.render(self.talk_status, True,
                               YELLOW if self.talk_active else TEXT)
        self.screen.blit(st, (rect.x + 16, rect.y + 38))
        self.talk_btn.draw(self.screen, self.small)
        self.parent_btn.draw(self.screen, self.small)

    def _log_panel(self, rect):
        panel(self.screen, rect, "事件")
        for i, ln in enumerate(self.logs):
            color = RED if "[警告]" in ln else (ACCENT if "[语音]" in ln else TEXT_DIM)
            self.screen.blit(self.tiny.render(ln, True, color), (rect.x + 14, rect.y + 36 + i * 19))

    def _draw(self):
        self._bg()
        self._title()

        # 左：速度表 + 踏板
        panel(self.screen, SPEED_PANEL)
        self._speedometer(185, 228, 112)
        panel(self.screen, PEDAL_PANEL, "踏板")
        self.throttle_pedal.draw(self.screen, self.font, self.small)
        self.brake_pedal.draw(self.screen, self.font, self.small)
        self.screen.blit(self.tiny.render("拖动踏板模拟踩踏", True, TEXT_DIM), (48, 600))

        # 中：中控台 + 能量条 + 灯光 + 数据
        panel(self.screen, CTRL_PANEL, "中控台")
        for b in self.btns.values():
            b.draw(self.screen, self.font)
        self.ebrk_btn.draw(self.screen, self.font)
        for i, b in enumerate(self.gear_btns):
            b.color = ACCENT if self.brain.gear == i + 1 else PANEL
            b.draw(self.screen, self.small)
        self.voice_btn.draw(self.screen, self.small)

        self._energy_bar(ENERGY_RECT)
        self._lights_row(LIGHT_RECT)
        self._data(DATA_RECT)

        # 右：摄像头 + 对讲 + 日志
        panel(self.screen, CAM_RECT, "摄像头")
        self.camera.draw(self.screen, self.ceb.speed, time.time())
        self.cam_btn.draw(self.screen, self.small)
        self._talk(TALK_RECT)
        self._log_panel(LOG_RECT)

        tip = self.tiny.render("点按钮 / 拖踏板 / 翻转摄像头 / 对讲", True, TEXT_DIM)
        self.screen.blit(tip, (30, H - 26))

    # ---------- 主循环 ----------
    def run(self):
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                for b in list(self.btns.values()) + self.gear_btns + \
                        [self.ebrk_btn, self.voice_btn, self.cam_btn, self.talk_btn, self.parent_btn]:
                    b.handle(event)
                self.throttle_pedal.handle(event)
                self.brake_pedal.handle(event)

            frame = self.brain.link.receive()
            if frame:
                self.brain.handle_frame(*frame)
            self.ceb.tick()

            self._draw()
            pygame.display.flip()
            self.clock.tick(30)

        self.brain.stop()
        if self.voice:
            self.voice.stop()
        self.engine.stop()
        pygame.quit()


def main():
    ap = argparse.ArgumentParser(description="干杯一号 · 桌面模拟器")
    ap.add_argument("--voice", action="store_true", help="启用真实语音控制")
    args = ap.parse_args()
    Simulator(voice=args.voice).run()


if __name__ == "__main__":
    main()
