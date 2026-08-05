"""模拟器摄像头：模拟行车记录 / vlog 画面。"""

import time

import pygame


class CameraView:
    """模拟摄像头画面。

    - 前视模式：动态路面 + 速度感条纹 + REC 角标 + 时间戳
    - 自拍模式（翻转）：显示模拟"驾驶员"（头盔 + 人形）
    """

    def __init__(self, rect, small_font):
        self.rect = pygame.Rect(rect)
        self.small = small_font
        self.flipped = False   # False=前视行车记录, True=自拍 vlog
        self.rec = True
        self._offset = 0.0

    def toggle(self):
        self.flipped = not self.flipped

    def draw(self, surface, speed, now):
        r = self.rect
        # 背景（天空 → 路面渐变）
        for i in range(r.h):
            c = (18 + int(i / r.h * 14), 21 + int(i / r.h * 16), 28 + int(i / r.h * 12))
            pygame.draw.line(surface, c, (r.x, r.y + i), (r.x + r.w, r.y + i))

        if self.flipped:
            self._draw_flipped(surface, r)
        else:
            self._draw_front(surface, r, speed)

        # 边框
        pygame.draw.rect(surface, (70, 80, 100), r, 2, border_radius=4)
        # REC 闪烁
        if self.rec and int(now * 2) % 2 == 0:
            pygame.draw.circle(surface, (255, 70, 70), (r.x + 18, r.y + 18), 6)
            t = self.small.render("REC", True, (255, 90, 90))
            surface.blit(t, (r.x + 30, r.y + 10))
        # 模式 + 时间
        mode = "自拍 VLOG" if self.flipped else "前视 · 行车记录"
        surface.blit(self.small.render(mode, True, (190, 200, 215)),
                     (r.x + r.w - 150, r.y + 10))
        surface.blit(self.small.render(time.strftime("%H:%M:%S"), True, (190, 200, 215)),
                     (r.x + 12, r.y + r.h - 22))

    def _draw_front(self, surface, r, speed):
        # 地平线
        hy = r.y + int(r.h * 0.38)
        pygame.draw.line(surface, (95, 108, 130), (r.x, hy), (r.right, hy), 1)
        # 路面（深色下半区）
        pygame.draw.rect(surface, (34, 40, 50), (r.x, hy, r.w, r.bottom - hy))
        # 中央车道线（随速度移动，产生前进感）
        cx = r.centerx
        self._offset = (self._offset + speed * 0.6) % 60
        for i in range(10):
            yy = hy + 10 + i * 30 + self._offset
            w = max(2, int(10 * (1 - (yy - hy) / (r.h - hy) * 0.8)))
            pygame.draw.line(surface, (180, 190, 205), (cx - w, yy), (cx + w, yy), 2)
        # 路边
        pygame.draw.line(surface, (150, 160, 175), (r.x + 20, hy), (r.x + 8, r.bottom), 2)
        pygame.draw.line(surface, (150, 160, 175), (r.right - 20, hy), (r.right - 8, r.bottom), 2)

    def _draw_flipped(self, surface, r):
        # 模拟驾驶员：头盔 + 脸 + 身体（面向镜头）
        cx, cy = r.centerx, r.y + int(r.h * 0.42)
        # 车身背景色带
        pygame.draw.rect(surface, (40, 46, 58), (r.x, cy + 30, r.w, r.bottom - cy - 30))
        # 头盔
        pygame.draw.circle(surface, (70, 95, 210), (cx, cy - 38), 26)
        pygame.draw.circle(surface, (110, 135, 235), (cx - 8, cy - 44), 10)
        # 脸
        pygame.draw.circle(surface, (222, 200, 178), (cx, cy), 28)
        # 眼睛
        pygame.draw.circle(surface, (40, 40, 50), (cx - 12, cy - 4), 4)
        pygame.draw.circle(surface, (40, 40, 50), (cx + 12, cy - 4), 4)
        # 嘴（微笑）
        pygame.draw.arc(surface, (190, 110, 110), (cx - 10, cy + 6, 20, 12), 0, 3.14, 2)
        # 身体
        pygame.draw.rect(surface, (52, 62, 80), (cx - 36, cy + 24, 72, 44), border_radius=12)
