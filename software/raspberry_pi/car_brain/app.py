"""大脑 CLI 入口。

用法：
  1) 连接真实/虚拟串口（COM3 或 /dev/ttyAMA0）：
     python -m car_brain.app --port COM3

  2) 直接启动 native 小脑 exe（无需 com0com，stdin/stdout 当串口）：
     python -m car_brain.app --native <小脑exe路径>

  3) --demo 自动演示：等待小脑就绪 → 设置档位 → 开灯 → 展示按钮事件
"""

import argparse
import logging
import sys
import time

from .brain import Brain
from .serial_link import SerialLink

# ---- 串口后端 ----
try:
    import serial as pyserial

    class SerialPort:
        def __init__(self, port, baud):
            self.ser = pyserial.Serial(port, baud, timeout=0.5)

        def read(self, size):
            return self.ser.read(size)

        def write(self, data):
            self.ser.write(data)

        def close(self):
            self.ser.close()
except ImportError:
    SerialPort = None


class SubprocessPort:
    """把 native 小脑 exe 的 stdin/stdout 当串口（Windows 无 com0com 也可联调）。"""

    def __init__(self, exe):
        import queue
        import subprocess
        import threading

        self._q = queue.Queue()
        self.proc = subprocess.Popen(
            [exe], stdin=subprocess.PIPE, stdout=subprocess.PIPE
        )
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def _read_loop(self):
        while True:
            chunk = self.proc.stdout.read(256)
            if not chunk:
                break
            self._q.put(chunk)

    def read(self, size, timeout=0.5):
        try:
            return self._q.get(timeout=timeout)
        except Exception:
            return b""

    def write(self, data):
        self.proc.stdin.write(data)
        self.proc.stdin.flush()

    def close(self):
        self.proc.terminate()


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    log = logging.getLogger("demo")

    ap = argparse.ArgumentParser(description="干杯一号 大脑")
    ap.add_argument("--port", help="串口名，如 COM3 / /dev/ttyAMA0")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--native", help="native 小脑 exe 路径")
    ap.add_argument("--demo", action="store_true", help="自动演示模式")
    ap.add_argument("--seconds", type=float, default=12.0, help="演示时长")
    args = ap.parse_args()

    if args.native:
        port = SubprocessPort(args.native)
        log.info("[大脑] 连接 native 小脑: %s", args.native)
    elif args.port:
        if SerialPort is None:
            log.error("未安装 pyserial，请先: pip install -r requirements.txt")
            sys.exit(1)
        port = SerialPort(args.port, args.baud)
        log.info("[大脑] 连接串口: %s @ %d", args.port, args.baud)
    else:
        ap.error("必须指定 --port 或 --native")

    link = SerialLink(port)
    brain = Brain(link)

    # 事件打印
    def on_event(event, data):
        if event == "ready":
            log.info("  · 小脑就绪 (协议 %s)", data)
        elif event == "status":
            log.info("  · 状态: %s", data)
        elif event == "light":
            log.info("  · 大灯 -> %s", "ON" if data else "OFF")
        elif event == "mute":
            log.info("  · 静音 -> %s", "ON" if data else "OFF")
        elif event == "seat":
            log.info("  · 就座 -> %s", "ON" if data else "OFF")
        elif event == "ebrk":
            log.info("  · ⚠️ 急刹触发")
        elif event == "offline":
            log.warning("  · ⚠️ 小脑离线!")
        elif event == "ack" and data != "OK":
            log.warning("  · 命令被拒: %s", data)
        else:
            log.info("  · %s %s", event, data)

    brain.on_event = on_event
    brain.start()

    # 事件循环 + 主动演示动作
    deadline = time.time() + args.seconds
    demo_step = 0
    last_action = time.time()

    try:
        while time.time() < deadline:
            frame = link.receive()
            if frame:
                cmd, params = frame
                brain.handle_frame(cmd, params)
            # 演示动作序列
            if args.demo and time.time() - last_action > 3.0:
                last_action = time.time()
                demo_step += 1
                if demo_step == 1:
                    log.info("[大脑] 语音指令: 设置 3 档")
                    brain.set_gear(3)
                elif demo_step == 2:
                    log.info("[大脑] 语音指令: 打开大灯")
                    brain.set_light(True)
                elif demo_step == 3:
                    log.info("[大脑] 语音指令: 静音")
                    brain.set_mute(True)
            time.sleep(0.02)
    except KeyboardInterrupt:
        pass
    finally:
        brain.stop()
        port.close()
        log.info("[大脑] 退出")


if __name__ == "__main__":
    main()
