"""大脑 ↔ 小脑 内存联调测试。

用两个线程 + 内存管道模拟真实串口，让 Brain（大脑）与
MiniCerebellum（模拟小脑）按协议完整对话，验证：
  1. READY 上电握手与状态同步
  2. 按钮事件上报 → 大脑决策 → 命令下发 → 小脑执行 + ACK
  3. 大脑主动命令（档位 / 灯光）被小脑正确执行

运行：python -m unittest discover -s tests -v
"""

import threading
import time
import unittest

from car_brain.brain import Brain
from car_brain.protocol import commands as C
from car_brain.serial_link import SerialLink


class Pipe:
    """内存管道：模拟 pyserial 串口对象（两个 Pipe 互为 peer）。"""

    def __init__(self, peer=None):
        self.peer = peer
        self.buf = b""
        self.lock = threading.Lock()

    def write(self, data):
        with self.peer.lock:
            self.peer.buf += data

    def read(self, size, timeout=0.2):
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self.lock:
                if self.buf:
                    chunk, self.buf = self.buf[:size], self.buf[size:]
                    return chunk
            time.sleep(0.005)
        return b""


class MiniCerebellum:
    """测试用模拟小脑：按协议响应大脑，并模拟按钮事件。"""

    def __init__(self, pipe):
        self.link = SerialLink(pipe)
        self.light = False
        self.gear = 2
        self.mute = False
        self.ack_count = 0
        self.ebrk = False
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()
        threading.Timer(0.1, lambda: self.link.send(C.READY, "V0.3")).start()
        threading.Timer(0.6, lambda: self.link.send(C.BTN, f"{C.LIGHT_BTN},PRESS")).start()

    def _run(self):
        while not self._stop.is_set():
            frame = self.link.receive()
            if not frame:
                continue
            cmd, params = frame
            if cmd == C.PING:
                self.link.send(C.PONG)
            elif cmd == C.LIGHT:
                self.light = (params == "ON")
                self.link.send(C.ACK, "OK")
                self.ack_count += 1
            elif cmd == C.GEAR:
                self.gear = int(params)
                self.link.send(C.ACK, "OK")
                self.ack_count += 1
            elif cmd == C.MUTE:
                self.mute = (params == "ON")
                self.link.send(C.ACK, "OK")
                self.ack_count += 1
            elif cmd == C.EBRK:
                self.ebrk = True
                self.link.send(C.ACK, "OK")
                self.ack_count += 1

    def stop(self):
        self._stop.set()


class TestBrainLoop(unittest.TestCase):
    def setUp(self):
        self.brain_pipe = Pipe()
        self.ceb_pipe = Pipe()
        self.brain_pipe.peer = self.ceb_pipe
        self.ceb_pipe.peer = self.brain_pipe

        self.ceb = MiniCerebellum(self.ceb_pipe)
        self.brain = Brain(SerialLink(self.brain_pipe))
        self.events = []
        self.brain.on_event = lambda ev, data: self.events.append((ev, data))
        self.ceb.start()

    def _pump(self, seconds):
        deadline = time.time() + seconds
        while time.time() < deadline:
            frame = self.brain.link.receive()
            if frame:
                self.brain.handle_frame(*frame)
            time.sleep(0.005)

    def test_readiness(self):
        self._pump(0.5)
        self.assertTrue(self.brain.cerebellum_online)
        self.assertIn("ready", [e[0] for e in self.events])

    def test_button_to_command_loop(self):
        # 小脑模拟按下大灯按钮 → 大脑应切换灯状态并下发 LIGHT:ON
        self._pump(0.8)
        self.assertTrue(self.brain.light)
        self.assertTrue(self.ceb.light)  # 小脑确实执行了
        self.assertGreaterEqual(self.ceb.ack_count, 1)

    def test_brain_active_commands(self):
        # 大脑主动设置档位与灯光
        self._pump(0.3)
        self.brain.set_gear(3)
        self._pump(0.3)
        self.assertEqual(self.ceb.gear, 3)

        self.brain.set_light(False)
        self._pump(0.3)
        self.assertFalse(self.ceb.light)

    def test_remote_ebrake(self):
        self._pump(0.3)
        self.brain.remote_ebrake()
        self._pump(0.3)
        self.assertTrue(self.brain.ebrk)
        self.assertTrue(self.ceb.ebrk)

    def tearDown(self):
        self.ceb.stop()


if __name__ == "__main__":
    unittest.main()
