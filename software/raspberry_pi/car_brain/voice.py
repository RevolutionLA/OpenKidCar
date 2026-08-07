"""语音控制模块（vosk 离线识别 + 可更换音色的语音反馈）。

用法（建议在 Python 3.13+ 虚拟环境运行）：
    .venv/Scripts/python.exe -m pip install -r requirements.txt
    .venv/Scripts/python.exe -m car_brain.app --native <小脑exe> --voice

语音交互（先说"干杯出来"唤醒，再说指令；也可一句话连说）：
    唤醒词 : 干杯出来

指令经 on_command(cmd, params) 回调输出。cmd 取值见 COMMAND_RULES；
另有特殊事件 __wake__（唤醒成功）。

【如何添加新指令】在下面 COMMAND_RULES 表中加一行即可，例如：
    (("关掉所有灯", "全部关灯"), ("light_all", "off")),
然后在 app.py 的 on_voice_command 里处理新的 cmd。
"""

import json
import os
import threading
import time

from .tts import TTS

MODEL_DEFAULT = None  # 由 default_model_path() 自动查找

# ============================================================
# 指令规则表：每行 = (匹配关键词元组, (指令名, 参数))
# 按顺序匹配，先匹配先执行。
# 【添加新指令】只需在此加一行，再在 app.py 的 on_voice_command 里处理新指令名。
# ============================================================
COMMAND_RULES = (
    # ---- 灯光 ----
    (("打开大灯", "开大灯", "打开车灯", "开灯", "亮灯"), ("light", "on")),
    (("关闭大灯", "关大灯", "关灯", "关闭车灯", "把灯关掉"), ("light", "off")),
    (("打开灯带", "开灯带", "灯带打开"), ("strip", "on")),
    (("关闭灯带", "关灯带", "灯带关闭"), ("strip", "off")),
    # ---- 静音 ----
    (("取消静音", "解除静音", "关闭静音", "恢复声音"), ("mute", "off")),
    (("静音", "安静"), ("mute", "on")),
    # ---- 档位 ----
    (("一档", "1档"), ("gear", 1)),
    (("二档", "2档"), ("gear", 2)),
    (("三档", "3档"), ("gear", 3)),
    (("四档", "4档"), ("gear", 4)),
    # ---- 喇叭 / 转向 ----
    (("鸣笛", "按喇叭", "响喇叭"), ("horn", "on")),
    (("停止鸣笛", "不鸣笛", "喇叭关"), ("horn", "off")),
    (("左转", "左转向", "打左转向"), ("turn", "L")),
    (("右转", "右转向", "打右转向"), ("turn", "R")),
    (("关闭转向", "关转向", "转向灯关"), ("turn", "off")),
    # ---- 急刹 ----
    (("刹车", "急刹", "紧急刹车", "停车"), ("ebrk", None)),
)


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


class VoiceController:
    def __init__(self, model_path=None, awake_timeout: float = 8.0, tts: TTS = None):
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
        self.always_awake = False   # 常开模式：开启后每条指令直接识别，无需反复唤醒
        self._stop = threading.Event()
        self._thread = None
        # 指令回调：on_command(cmd, params)
        self.on_command = None
        # 状态回调：on_status(text)（唤醒/执行反馈）
        self.on_status = None
        # 语音反馈
        self.tts = tts or TTS()

    # ---------------- 指令解析 ----------------
    def _contains_wake(self, text: str) -> bool:
        return "干杯" in text

    def _match_command(self, text: str):
        # 按关键词长度降序匹配：先匹配长的、具体的（如"打开灯带"），
        # 避免被短关键词（如"开灯"）误匹配。
        rules = [(kw, cmd) for keywords, cmd in COMMAND_RULES for kw in keywords]
        rules.sort(key=lambda x: len(x[0]), reverse=True)
        for kw, cmd in rules:
            if kw in text:
                return cmd
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
        if not self.always_awake:
            self.awake = False
        return cmd

    # ---------------- 识别主循环 ----------------
    def _process(self, text: str):
        # 上报识别原文（便于排查：看 vosk 实际识别成了什么）
        if self.on_status:
            self.on_status(f"识别: {text}")
        result = self._handle_text(text)
        if not result:
            return
        cmd, params = result
        if cmd == "__wake__":
            if self.on_status:
                self.on_status("已唤醒，请说指令")
            self.tts.speak("我在，请说指令")
        elif self.on_command:
            if self.on_status:
                self.on_status(f"指令: {cmd} {params}")
            self.on_command(cmd, params)
            self.tts.speak("好的")

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
