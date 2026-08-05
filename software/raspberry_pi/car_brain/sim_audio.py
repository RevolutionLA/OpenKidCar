"""模拟器音频：引擎轰鸣实时合成 + 对讲模拟。"""

import numpy as np
import sounddevice as sd


class EngineSound:
    """实时合成引擎轰鸣。

    油门越大 → 转速（基频）越高、音量越大、谐波越丰富。
    怠速时是低沉的隆隆声。
    """

    def __init__(self, samplerate: int = 44100):
        self._sr = samplerate
        self.throttle = 0
        self.mute = False
        self._phase = 0.0
        self._stream = None

    def start(self) -> bool:
        try:
            self._stream = sd.OutputStream(
                samplerate=self._sr, channels=2, dtype="float32",
                blocksize=1024, callback=self._callback,
            )
            self._stream.start()
            return True
        except Exception as e:
            print(f"[音效] 引擎声启动失败: {e}")
            self._stream = None
            return False

    def _callback(self, outdata, frames, time_info, status):
        thr = 0.0 if self.mute else self.throttle / 100.0
        rpm = 28 + thr * 240          # 基频 28Hz(怠速) ~ 268Hz(全油门)
        vol = 0.04 + thr * 0.13       # 音量随油门
        t = self._phase + np.arange(frames) / self._sr
        self._phase = (self._phase + frames / self._sr) % 1.0
        s = (
            0.55 * np.sin(2 * np.pi * rpm * t)
            + 0.28 * np.sin(2 * np.pi * rpm * 2 * t)
            + 0.12 * np.sin(2 * np.pi * rpm * 3 * t)
            + 0.05 * np.random.randn(frames)
        )
        s *= vol
        outdata[:] = np.column_stack([s, s])

    def set_throttle(self, v):
        self.throttle = max(0, min(100, int(v)))

    def set_mute(self, m):
        self.mute = bool(m)

    def stop(self):
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
