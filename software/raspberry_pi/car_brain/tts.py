"""语音反馈（TTS）模块 —— 可更换音色。

音色方案：
  - edge（默认，需联网生成一次，之后离线播放）：
      微软 edge-tts 神经语音，中文"晓晓"（zh-CN-XiaoxiaoNeural），音质自然。
      首次说某句话会联网生成 mp3 并缓存到 ~/opkidcar_tts，之后离线播放。
      用环境变量 TTS_VOICE 可换音色，如：
        zh-CN-XiaoxiaoNeural  晓晓（女声，默认）
        zh-CN-YunxiNeural     云希（男声）
        zh-CN-YunyangNeural   云扬（男声，新闻）
        zh-CN-XiaoyiNeural    晓伊（女声）
  - sapi：Windows 系统语音（离线，音色一般）。
      可在 Windows"设置 > 时间和语言 > 语音"中安装更多语音包。

引擎选择：默认 auto —— 装了 edge-tts 用 edge，否则 sapi；edge 联网失败自动回退 sapi。
"""

import os
import subprocess

CACHE_DIR = os.path.expanduser("~/opkidcar_tts")
DEFAULT_VOICE = os.environ.get("TTS_VOICE", "zh-CN-XiaoxiaoNeural")


def _speak_sapi(text: str):
    """Windows 系统语音（离线）。"""
    safe = text.replace("'", " ")
    ps = (
        "Add-Type -AssemblyName System.Speech; "
        "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "$s.Rate=0; $s.Volume=100; "
        f"$s.Speak('{safe}')"
    )
    subprocess.Popen(["powershell", "-NoProfile", "-Command", ps])


def _edge_available() -> bool:
    try:
        import edge_tts  # noqa: F401
        return True
    except ImportError:
        return False


def _play_mp3(path: str) -> bool:
    """播放 mp3（异步，后台线程）。优先 pygame，失败用系统默认播放器。"""
    try:
        import pygame

        if not pygame.mixer.get_init():
            pygame.mixer.init()
        pygame.mixer.music.stop()
        pygame.mixer.music.load(path)
        pygame.mixer.music.play()
        return True
    except Exception:
        # 兜底：系统默认播放器
        try:
            os.startfile(path)  # type: ignore[attr-defined]
            return True
        except Exception:
            return False


def _speak_edge(text: str) -> bool:
    try:
        import asyncio

        import edge_tts

        os.makedirs(CACHE_DIR, exist_ok=True)
        cache = os.path.join(CACHE_DIR, f"{abs(hash(text))}.mp3")
        if not os.path.exists(cache):
            asyncio.run(edge_tts.Communicate(text, DEFAULT_VOICE).save(cache))
        _play_mp3(cache)
        return True
    except Exception:
        return False


class TTS:
    def __init__(self, engine: str = "auto"):
        """engine: auto / edge / sapi。"""
        if engine == "auto":
            engine = "edge" if _edge_available() else "sapi"
        self.engine = engine

    def speak(self, text: str):
        if self.engine == "edge" and not _speak_edge(text):
            _speak_sapi(text)  # 联网/生成失败自动回退系统语音
        elif self.engine == "sapi":
            _speak_sapi(text)
