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
    ap.add_argument("--voice", action="store_true", help="启用语音控制（需 vosk + 麦克风）")
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

    # ---- 语音控制（可选）----
    vc = None
    if args.voice:
        try:
            from .voice import VoiceController

            vc = VoiceController()
        except ImportError as e:
            log.error("语音库未安装: %s", e)
            log.error("请在 Python 3.13 虚拟环境安装后运行：")
            log.error("  .venv/Scripts/python.exe -m pip install vosk sounddevice")
            sys.exit(1)
        except FileNotFoundError as e:
            log.error("%s", e)
            sys.exit(1)

        def on_voice_command(cmd, params):
            if cmd == "light":
                log.info("[语音] 灯光指令 -> %s", "ON" if params == "on" else "OFF")
                brain.set_light(params == "on")
            elif cmd == "mute":
                log.info("[语音] 静音指令 -> %s", "ON" if params == "on" else "OFF")
                brain.set_mute(params == "on")
            elif cmd == "gear":
                log.info("[语音] 档位指令 -> %d 档", params)
                brain.set_gear(params)
            elif cmd == "ebrk":
                log.info("[语音] 急刹指令")
                brain.remote_ebrake()
            elif cmd == "strip":
                log.info("[语音] 灯带指令 -> %s", params)
                brain.set_strip(1 if params == "on" else 0)
            elif cmd == "horn":
                log.info("[语音] 鸣笛指令 -> %s", params)
                brain.set_horn(params == "on")
            elif cmd == "turn":
                log.info("[语音] 转向指令 -> %s", params)
                brain.set_turn(params)

        def on_voice_status(text):
            log.info("[语音] %s", text)

        vc.on_command = on_voice_command
        vc.on_status = on_voice_status
        vc.start()
        log.info("[大脑] 语音已开启 —— 说\"干杯出来\"唤醒，然后说\"打开大灯\"等指令")

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
            # 自动演示动作序列（仅 --demo 时）
            if args.demo and time.time() - last_action > 3.0:
                last_action = time.time()
                demo_step += 1
                if demo_step == 1:
                    log.info("[大脑] 演示指令: 设置 3 档")
                    brain.set_gear(3)
                elif demo_step == 2:
                    log.info("[大脑] 演示指令: 打开大灯")
                    brain.set_light(True)
                elif demo_step == 3:
                    log.info("[大脑] 演示指令: 静音")
                    brain.set_mute(True)
            time.sleep(0.02)
    except KeyboardInterrupt:
        pass
    finally:
        if vc:
            vc.stop()
        brain.stop()
        port.close()
        log.info("[大脑] 退出")


if __name__ == "__main__":
    main()
