"""语音控制模块（vosk 离线识别，不依赖网络）。

用法（建议在 Python 3.13+ 虚拟环境运行）：
    .venv/Scripts/python.exe -m pip install vosk sounddevice
    .venv/Scripts/python.exe -m car_brain.app --native <小脑exe> --voice

语音交互（先说"干杯出来"唤醒，再说指令；也可一句话连说）：
    唤醒词 : 干杯出来
    灯光   : 打开大灯 / 关灯
    静音   : 静音 / 取消静音
    档位   : 一档 / 二档 / 三档 / 四档
    急刹   : 刹车 / 急刹

指令经 on_command(cmd, params) 回调输出，由上层接到大脑命令。
cmd 取值：light / mute / gear / ebrk；另有特殊事件 __wake__（唤醒成功）。
"""

import json
import os
import subprocess
import threading
import time

MODEL_DEFAULT = None  # 由 default_model_path() 自动查找


def default_model_path():
    """查找 vosk 中文模型目录。可通过环境变量 VOSK_MODEL 指定。"""
    env = os.environ.get("VOSK_MODEL")
    if env and os.path.isdir(env):
        return env
    candidates = [
        os.path.expanduser("~/vosk-model-small-cn-0.22"),
        os.path.expanduser("~/vosk-model-cn-0.22"),
    ]
    for p in candidates:
        if os.path.isdir(p):
            return p
    return None


def _speak(text):
    """Windows 系统语音反馈（可选，失败静默）。"""
    try:
        safe = text.replace("'", " ")
        subprocess.Popen(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Add-Type -AssemblyName System.Speech; "
                f"(New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak('{safe}')",
            ]
        )
    except Exception:
        pass


class VoiceController:
    def __init__(self, model_path=None, awake_timeout: float = 8.0):
        import sounddevice  # 延迟导入，避免无语音环境崩溃
        from vosk import KaldiRecognizer, Model

        path = model_path or default_model_path()
        if not path:
            raise FileNotFoundError(
                "未找到 vosk 中文模型。请下载 vosk-model-small-cn-0.22 解压到 ~/vosk-model-small-cn-0.22，"
                "或设置环境变量 VOSK_MODEL 指向模型目录。"
            )
        self._sd = sounddevice
        self._rec = KaldiRecognizer(Model(path), 16000)
        self.awake_timeout = awake_timeout
        self.awake = False
        self._awake_until = 0.0
        self._stop = threading.Event()
        self._thread = None
        # 指令回调：on_command(cmd, params)
        self.on_command = None
        # 状态回调：on_status(text)（唤醒/执行反馈）
        self.on_status = None

    # ---------------- 指令解析 ----------------
    def _contains_wake(self, text: str) -> bool:
        return "干杯" in text

    def _match_command(self, text: str):
        if any(k in text for k in ("打开大灯", "开大灯", "打开车灯", "开灯", "亮灯")):
            return ("light", "on")
        if any(k in text for k in ("关闭大灯", "关大灯", "关灯", "关闭车灯", "把灯关")):
            return ("light", "off")
        # 注意："取消静音"也含"静音"，取消类必须优先判断
        if any(k in text for k in ("取消静音", "解除静音", "关闭静音", "恢复声音")):
            return ("mute", "off")
        if "静音" in text or "安静" in text:
            return ("mute", "on")
        if "一档" in text or "1档" in text:
            return ("gear", 1)
        if "二档" in text or "2档" in text:
            return ("gear", 2)
        if "三档" in text or "3档" in text:
            return ("gear", 3)
        if "四档" in text or "4档" in text:
            return ("gear", 4)
        if any(k in text for k in ("急刹", "紧急刹", "刹车", "停车")):
            return ("ebrk", None)
        return None

    def _handle_text(self, text: str):
        text = text.replace(" ", "").replace("　", "")
        if not text:
            return None
        if not self.awake:
            if self._contains_wake(text):
                self.awake = True
                self._awake_until = time.time() + self.awake_timeout
                # 允许一句话连说：唤醒 + 指令（"干杯出来，开灯"）
                cmd = self._match_command(text)
                if cmd:
                    self.awake = False
                    return cmd
                return ("__wake__", None)
            return None
        # 已唤醒，等待指令
        if time.time() > self._awake_until:
            self.awake = False
            return None
        cmd = self._match_command(text)
        self.awake = False
        return cmd

    # ---------------- 识别主循环 ----------------
    def _process(self, text: str):
        result = self._handle_text(text)
        if not result:
            return
        cmd, params = result
        if cmd == "__wake__":
            if self.on_status:
                self.on_status("已唤醒，请说指令")
            _speak("我在，请说指令")
        elif self.on_command:
            if self.on_status:
                self.on_status(f"指令: {cmd} {params}")
            self.on_command(cmd, params)
            _speak("好的")

    def listen_loop(self):
        sd = self._sd
        with sd.InputStream(
            samplerate=16000, channels=1, dtype="int16", blocksize=4000
        ) as stream:
            while not self._stop.is_set():
                data, _ = stream.read(4000)
                if self._rec.AcceptWaveform(data.tobytes()):
                    text = json.loads(self._rec.Result()).get("text", "")
                    if text:
                        self._process(text)

    # ---------------- 生命周期 ----------------
    def start(self):
        self._thread = threading.Thread(target=self.listen_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
