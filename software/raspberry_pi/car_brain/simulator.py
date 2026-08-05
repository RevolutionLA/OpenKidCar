"""干杯一号 · 桌面模拟器（pygame 可视化驾驶舱）

复用现有大脑（Brain）与协议，内置一个"小脑引擎"模拟硬件。
界面为深色 HUD 驾驶舱风格：
  - 圆形速度表（弧形 + 指针）
  - 中控台按钮（大灯/静音/灯带/喇叭/急刹 + 档位）
  - 油门 / 刹车踏板（鼠标拖动模拟踩踏）
  - 电机发光能量条 + 灯光指示
  - 车辆数据（电压/温度/电流）+ 事件日志
  - 语音控制：可选连接真实麦克风（--voice）

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


# ============ 配色（深色 HUD 驾驶舱） ============
BG = (13, 17, 23)
PANEL = (20, 26, 34)
PANEL_LINE = (42, 53, 68)
TEXT = (232, 238, 244)
TEXT_DIM = (140, 156, 173)
ACCENT = (56, 189, 248)     # 亮蓝
CYAN = (34, 211, 238)       # 青
GREEN = (52, 211, 153)      # 绿（电机）
YELLOW = (251, 191, 36)     # 黄（刹车）
RED = (248, 113, 113)       # 红（危险）
GRID = (26, 33, 44)

W, H = 920, 660


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
    """模拟小脑：油门/刹车/按钮 + 执行大脑命令 + 状态上报。"""

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
        self._ready = False

    def press_button(self, name):
        self.link.send(C.BTN, f"{name},PRESS")

    def set_throttle(self, v):
        self.throttle = max(0, min(100, int(v)))

    def set_brake(self, v):
        self.brake = max(0, min(100, int(v)))

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
            self.ebrk = True
            self.brake = 100
            self._ack()

    def _ack(self):
        self.link.send(C.ACK, "OK")

    def _report(self):
        self.speed = self.throttle * GEAR_SPEED_MAX.get(self.gear, 10) * 70 // 10000
        self.motor = 0 if (self.ebrk or self.brake > 10) else self.throttle
        self.brake_light = 255 if (self.ebrk or self.brake > 10) else 0
        self.current = self.motor * 0.05
        params = (
            f"{self.speed},{self.throttle},{self.gear},"
            f"{self.voltage:.1f},{self.temp},{self.current:.1f}"
        )
        self.link.send(C.STAT, params)


# ============ 绘制工具 ============
def glow(surface, center, radius, color, alpha=90):
    """在 surface 上画一个柔和的发光晕。"""
    s = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
    for r in range(radius, 0, -3):
        a = int(alpha * (1 - r / radius))
        pygame.draw.circle(s, (*color, a), (radius, radius), r)
    surface.blit(s, (center[0] - radius, center[1] - radius))


def hgrad(surface, rect, c1, c2):
    """水平渐变。"""
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
    def __init__(self, rect, label, on_click=None, color=PANEL, text_color=TEXT):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.on_click = on_click
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
        # 高光顶边（立体感）
        top = pygame.Rect(self.rect.x + 4, self.rect.y + 3, self.rect.w - 8, 3)
        pygame.draw.rect(surface, (*c,), top, border_radius=2)
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
            self.pressed = False
        return False


class Pedal:
    """踏板：垂直拖动，底部向上填充。"""

    def __init__(self, rect, label, color, on_change):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.color = color
        self.on_change = on_change
        self.value = 0
        self._drag = False

    def draw(self, surface, font, small):
        # 底座
        pygame.draw.rect(surface, PANEL, self.rect.inflate(24, 24), border_radius=16)
        pygame.draw.rect(surface, PANEL_LINE, self.rect.inflate(24, 24), 1, border_radius=16)
        # 填充
        fh = int(self.rect.h * self.value / 100)
        fill = pygame.Rect(self.rect.x, self.rect.bottom - fh, self.rect.w, fh)
        if fh > 0:
            hgrad(surface, fill, tuple(int(c * 0.6) for c in self.color), self.color)
            glow(surface, fill.center, 18, self.color, 40)
            # 顶部圆弧亮边
            pygame.draw.rect(surface, tuple(min(255, c + 50) for c in self.color),
                             (fill.x, fill.y, fill.w, 3), border_radius=2)
        # 踏板面
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
        self.big = _load_font(52)
        self.title_font = _load_font(26)
        self.tiny = _load_font(15)

        # 大脑 + 小脑引擎（内存管道）
        self.bp, self.cp = Pipe(), Pipe()
        self.bp.peer, self.cp.peer = self.cp, self.bp
        self.ceb = CerebellumSim(self.cp)
        self.brain = Brain(SerialLink(self.bp))
        self.brain.on_event = self._on_brain_event
        self.brain.start()

        self.logs = []
        self._make_widgets()
        self.voice = None
        if voice:
            self._setup_voice()

    # ---------- 控件 ----------
    def _make_widgets(self):
        self.btns = {}
        # 中控台按钮（2 列 × 2 行）
        defs = [
            ("大灯", "LIGHT_BTN", PANEL),
            ("静音", "MUTE_BTN", PANEL),
            ("灯带", "STRIP_BTN", PANEL),
            ("喇叭", "HORN_BTN", PANEL),
        ]
        base_x, base_y, bw, bh, gap = 370, 60, 130, 52, 14
        for i, (label, name, color) in enumerate(defs):
            x = base_x + (i % 2) * (bw + gap)
            y = base_y + (i // 2) * (bh + gap)
            self.btns[name] = Button((x, y, bw, bh), label, lambda n=name: self.ceb.press_button(n), color)

        # 急刹（大红按钮）
        self.ebrk_btn = Button((370, 60 + (bh + gap) * 2, bw * 2 + gap, 46), "急 刹",
                               lambda: self.ceb.press_button("EBRK_BTN"), RED)

        # 档位
        self.gear_btns = []
        for g in range(1, 5):
            x = 370 + (g - 1) * 60
            self.gear_btns.append(Button((x, 60 + (bh + gap) * 2 + 62, 54, 40), f"{g}档",
                                         lambda gg=g: self.brain.set_gear(gg)))

        # 语音按钮
        self.voice_btn = Button((370 + 4 * 60, 60 + (bh + gap) * 2 + 62, 158, 40),
                                "语音:开灯", self._simulate_voice, (40, 66, 58))

        # 踏板
        self.throttle = Pedal((70, 470, 110, 150), "油门", GREEN, self.ceb.set_throttle)
        self.brake = Pedal((210, 470, 110, 150), "刹车", YELLOW, self.ceb.set_brake)

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
            self._log("[语音] 语音已开启：说「干杯出来」唤醒")
        except Exception as e:
            self._log(f"[语音] 语音启动失败: {e}")

    def _simulate_voice(self):
        self._log("[语音] 识别: 干杯出来开灯")
        self.brain.set_light(True)

    def _on_brain_event(self, event, data):
        if event == "light":
            self._log(f"大灯 -> {'开' if data else '关'}")
        elif event == "mute":
            self._log(f"静音 -> {'开' if data else '关'}")
        elif event == "ebrk":
            self._log("[警告] 急刹触发！")

    def _log(self, msg):
        self.logs.append(msg)
        if len(self.logs) > 5:
            self.logs.pop(0)

    # ---------- 绘制 ----------
    def _bg(self):
        self.screen.fill(BG)
        # 网格线（速度感）
        for x in range(0, W, 48):
            pygame.draw.line(self.screen, GRID, (x, 0), (x, H))
        for y in range(0, H, 48):
            pygame.draw.line(self.screen, GRID, (0, y), (W, y))
        # 底部渐晕
        for i in range(90):
            a = int(40 * (1 - i / 90))
            pygame.draw.line(self.screen, (20, 24, 32), (0, H - i), (W, H - i))

    def _title(self):
        t = self.title_font.render("干杯一号 · 桌面模拟器", True, TEXT)
        self.screen.blit(t, (30, 24))
        st = self.small.render("GANBEI NO.1", True, TEXT_DIM)
        self.screen.blit(st, (34, 56))
        status = self.small.render(
            "大脑 ● 在线" if self.brain.cerebellum_online else "大脑 ● 连接中",
            True, GREEN if self.brain.cerebellum_online else YELLOW)
        self.screen.blit(status, (W - 220, 34))

    def _speedometer(self, cx, cy, r):
        # 表盘
        rect = pygame.Rect(cx - r, cy - r, r * 2, r * 2)
        pygame.draw.circle(self.screen, PANEL, (cx, cy), r)
        pygame.draw.circle(self.screen, PANEL_LINE, (cx, cy), r, 2)
        # 发光
        glow(self.screen, (cx, cy), r, CYAN, 26 if self.ceb.speed == 0 else 70)

        # 刻度弧：-225° ~ 45°（下方开口）
        a0, a1 = math.radians(-225), math.radians(45)
        speed_frac = min(1.0, self.ceb.speed / 25.0)
        # 背景弧
        pygame.draw.arc(self.screen, PANEL_LINE, rect.inflate(-14, -14), a0, a1, 8)
        # 进度弧
        if speed_frac > 0:
            c = GREEN if speed_frac < 0.5 else (CYAN if speed_frac < 0.85 else RED)
            pygame.draw.arc(self.screen, c, rect.inflate(-14, -14), a0, a0 + (a1 - a0) * speed_frac, 8)

        # 刻度
        for i in range(9):
            ang = a0 + (a1 - a0) * i / 8
            px, py = cx + (r - 22) * math.cos(ang), cy + (r - 22) * math.sin(ang)
            tx, ty = cx + (r - 34) * math.cos(ang), cy + (r - 34) * math.sin(ang)
            pygame.draw.line(self.screen, TEXT_DIM, (px, py), (tx, ty), 2)

        # 指针
        if speed_frac > 0:
            ang = a0 + (a1 - a0) * speed_frac
            ex, ey = cx + (r - 38) * math.cos(ang), cy + (r - 38) * math.sin(ang)
            pygame.draw.line(self.screen, RED, (cx, cy), (ex, ey), 4)
            pygame.draw.circle(self.screen, RED, (cx, cy), 6)

        # 速度数字
        sv = self.big.render(str(self.ceb.speed), True, TEXT)
        self.screen.blit(sv, sv.get_rect(center=(cx, cy + 4)))
        u = self.small.render("km/h", True, TEXT_DIM)
        self.screen.blit(u, u.get_rect(center=(cx, cy + 40)))
        g = self.small.render(f"档位 {self.ceb.gear} 档", True, ACCENT)
        self.screen.blit(g, g.get_rect(center=(cx, cy + 66)))

    def _energy_bar(self, rect):
        """电机能量条（发光渐变）。"""
        panel(surface=self.screen, rect=rect)
        label = self.small.render("电机输出", True, TEXT_DIM)
        self.screen.blit(label, (rect.x + 14, rect.y + 12))
        # 轨道
        bar = pygame.Rect(rect.x + 14, rect.y + 42, rect.w - 28, 22)
        pygame.draw.rect(self.screen, (30, 38, 48), bar, border_radius=11)
        pct = self.ceb.motor / 100
        if pct > 0:
            fill = pygame.Rect(bar.x, bar.y, int(bar.w * pct), bar.h)
            hgrad(self.screen, fill, (28, 120, 120), GREEN if pct < 0.7 else YELLOW)
            pygame.draw.rect(self.screen, GREEN, fill, border_radius=11)
            glow(self.screen, (fill.right, bar.centery), 26, GREEN, 50)
        pv = self.font.render(f"{self.ceb.motor}%", True, TEXT)
        self.screen.blit(pv, pv.get_rect(center=(bar.centerx, bar.centery)))

    def _lights_row(self, x, y):
        """灯光指示（发光圆点）。"""
        items = [
            ("大灯", GREEN if self.ceb.light else TEXT_DIM, self.ceb.light),
            ("灯带", CYAN if self.ceb.strip else TEXT_DIM, self.ceb.strip),
            ("转向", (ACCENT if self.ceb.turn in ("L", "R") else TEXT_DIM), self.ceb.turn in ("L", "R")),
            ("刹车灯", RED if self.ceb.brake_light else TEXT_DIM, self.ceb.brake_light),
        ]
        for i, (name, color, on) in enumerate(items):
            cx = x + i * 96 + 30
            cy = y + 22
            if on:
                glow(self.screen, (cx, cy), 16, color, 80)
            pygame.draw.circle(self.screen, color if on else (45, 52, 64), (cx, cy), 7)
            pygame.draw.circle(self.screen, PANEL_LINE, (cx, cy), 7, 1)
            self.screen.blit(self.tiny.render(name, True, TEXT_DIM), (cx - 16, cy + 14))

    def _draw(self):
        self._bg()
        self._title()

        # ---- 左列：速度表 + 踏板 ----
        panel(self.screen, pygame.Rect(30, 90, 310, 300))
        self._speedometer(185, 230, 118)
        panel(self.screen, pygame.Rect(30, 405, 310, 220), "踏板")
        self.throttle.draw(self.screen, self.font, self.small)
        self.brake.draw(self.screen, self.font, self.small)
        tip = self.tiny.render("鼠标拖动踏板模拟踩踏", True, TEXT_DIM)
        self.screen.blit(tip, (48, 588))

        # ---- 中控台 ----
        ctl = pygame.Rect(370, 40, 520, 210)
        panel(self.screen, ctl, "中控台")
        for b in self.btns.values():
            b.draw(self.screen, self.font)
        self.ebrk_btn.draw(self.screen, self.font)
        for i, b in enumerate(self.gear_btns):
            b.color = ACCENT if self.brain.gear == i + 1 else PANEL
            b.draw(self.screen, self.small)
        self.voice_btn.draw(self.screen, self.small)

        # ---- 电机 + 灯光 ----
        self._energy_bar(pygame.Rect(370, 268, 520, 96))
        panel(self.screen, pygame.Rect(370, 378, 520, 66))
        self._lights_row(390, 400)

        # ---- 车辆数据 ----
        data = pygame.Rect(370, 458, 520, 80)
        panel(self.screen, data)
        cells = [
            (f"{self.ceb.voltage:.1f}V", "电压"),
            (f"{self.ceb.temp}℃", "温度"),
            (f"{self.ceb.current:.1f}A", "电流"),
            ("行驶中" if self.ceb.speed > 0 else "静止", "状态"),
        ]
        for i, (val, name) in enumerate(cells):
            x = data.x + 20 + i * 120
            self.screen.blit(self.font.render(val, True, TEXT), (x, data.y + 14))
            self.screen.blit(self.tiny.render(name, True, TEXT_DIM), (x, data.y + 42))

        # ---- 日志 ----
        log_rect = pygame.Rect(370, 552, 520, 82)
        panel(self.screen, log_rect, "事件")
        for i, ln in enumerate(self.logs):
            color = RED if "[警告]" in ln else (ACCENT if "[语音]" in ln else TEXT_DIM)
            self.screen.blit(self.tiny.render(ln, True, color), (log_rect.x + 14, log_rect.y + 34 + i * 19))

    # ---------- 主循环 ----------
    def run(self):
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                for b in list(self.btns.values()) + self.gear_btns + [self.ebrk_btn, self.voice_btn]:
                    b.handle(event)
                self.throttle.handle(event)
                self.brake.handle(event)

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
        pygame.quit()


def main():
    ap = argparse.ArgumentParser(description="干杯一号 · 桌面模拟器")
    ap.add_argument("--voice", action="store_true", help="启用真实语音控制")
    args = ap.parse_args()
    Simulator(voice=args.voice).run()


if __name__ == "__main__":
    main()
