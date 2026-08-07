#!/usr/bin/env python3
"""小智语音桥接进程（独立进程，用 py-xiaozhi 的 Python 3.11 环境运行）。

职责：
  - 提供本地 WebSocket 服务（端口 8010，/xiaozhi）
  - 内部连接小智官方服务器（复用 py-xiaozhi 的 WebsocketProtocol）
  - 把小车端网页的 PCM 音频编码成 Opus 发小智，小智回复解码回传

运行（在 software/raspberry_pi 目录）：
  py-xiaozhi/.venv/Scripts/python.exe digital_twin/backend/xiaozhi_bridge.py [端口]

通信协议（JSON 文本帧）：
  收：{"type":"xiaozhi","action":"start"} / {"action":"audio","data":"<base64 pcm16>"} / {"action":"stop"}
  发：{"type":"xiaozhi_reply","data":"<base64 pcm16>"} / {"type":"xiaozhi_log","text":"..."}
"""

import asyncio
import base64
import json
import os
import sys

import numpy as np

# 把 py-xiaozhi 加入 sys.path（本脚本用 py-xiaozhi 的 venv 运行，src 包可导入）
_PY_XIAOZHI = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "py-xiaozhi")
)
sys.path.insert(0, _PY_XIAOZHI)

from aiohttp import web

# ---- py-xiaozhi 初始化 ----
from src.utils.config_manager import initialize_config
initialize_config()
from src.utils.opus_loader import setup_opus
setup_opus()

from src.constants.constants import ListeningMode
from src.protocols.websocket_protocol import WebsocketProtocol
from src.audio_codecs.opus_codec import OpusCodec


class XiaozhiSession:
    """连接小智服务器，处理一段对话。"""

    def __init__(self, on_audio, on_log):
        self.protocol = WebsocketProtocol()
        self.codec = OpusCodec(16000, 24000, 1)  # 16k 编码，24k 解码
        self.codec.initialize()
        self.on_audio = on_audio      # async (base64 pcm)
        self.on_log = on_log          # (text)
        self.connected = False
        self._ready_event = asyncio.Event()

        self.protocol.on_incoming_audio(self._handle_incoming_audio)
        self.protocol.on_incoming_json(self._handle_incoming_json)
        self.protocol.on_network_error(self._handle_network_error)
        self.protocol.on_audio_channel_opened(self._channel_opened)
        self.protocol.on_audio_channel_closed(self._channel_closed)

    async def _channel_opened(self):
        self.connected = True
        self._ready_event.set()
        await self.on_log("小智服务器已连接")

    async def _channel_closed(self):
        self.connected = False
        await self.on_log("小智连接已断开")

    async def _handle_network_error(self, msg):
        await self.on_log(f"小智网络错误: {msg}")

    def _handle_incoming_json(self, data):
        t = data.get("type", "")
        if t == "tts":
            state = data.get("state", "")
            # 可在这里触发 UI 提示（可选）
            pass

    def _handle_incoming_audio(self, data: bytes):
        # 小智返回的 Opus 帧 → 解码成 float32 PCM
        try:
            from src.audio_codecs.opus_codec import parse_opus_toc
            info = parse_opus_toc(data)
            if info is None:
                return
            # 关键：用 duration_ms（整包总时长，含多帧），不是 frame_ms！
            # 与 py-xiaozhi 官方 audio_codec.write_audio 保持一致
            frame_size = int(24000 * info["duration_ms"] / 1000)
            pcm = self.codec.decode(data, frame_size)
            # float32 → int16（必须 clip，防溢出爆音/电音！）
            pcm16 = np.clip(pcm, -1.0, 1.0)
            pcm16 = (pcm16 * 32767).astype("<i2").tobytes()
            b64 = base64.b64encode(pcm16).decode()
            asyncio.get_event_loop().create_task(self.on_audio(b64))
        except Exception as e:
            print(f"[小智] 解码回复失败: {e}", flush=True)

    # ---------- 供桥接 WS 调用 ----------
    async def connect(self):
        try:
            await asyncio.wait_for(self.protocol.open_audio_channel(), timeout=12)
            return True
        except Exception as e:
            await self.on_log(f"连接小智失败: {e}")
            return False

    async def start_listening(self):
        if not self.connected:
            ok = await self.connect()
            if not ok:
                return
        await self.protocol.send_start_listening(ListeningMode.MANUAL)
        await self.on_log("🎙 说话中，请按着说…")

    async def send_audio_b64(self, b64: str):
        if not self.connected:
            return
        pcm16 = base64.b64decode(b64)
        # int16 → float32
        pcm_f32 = np.frombuffer(pcm16, dtype="<i2").astype(np.float32) / 32768.0
        sent = 0
        # 按 320 样本/帧编码
        for i in range(0, len(pcm_f32), 320):
            chunk = pcm_f32[i:i + 320]
            if len(chunk) < 320:
                # 补零到整帧
                pad = np.zeros(320 - len(chunk), dtype=np.float32)
                chunk = np.concatenate([chunk, pad])
            opus = self.codec.encode(chunk, 320)
            await self.protocol.send_audio(opus)
            sent += 1

    async def stop_listening(self):
        if self.connected:
            await self.protocol.send_stop_listening()
        await self.on_log("✅ 已结束，等待小智回复…")


# ================= 桥接 WebSocket 服务 =================
class BridgeServer:
    def __init__(self):
        self.session = None
        self.clients = set()

    async def _send(self, msg):
        text = json.dumps(msg, ensure_ascii=False)
        for ws in list(self.clients):
            try:
                await ws.send_str(text)
            except Exception:
                self.clients.discard(ws)

    async def _log(self, text):
        print(f"[小智] {text}", flush=True)
        await self._send({"type": "xiaozhi_log", "text": text})

    async def _reply_audio(self, b64):
        await self._send({"type": "xiaozhi_reply", "data": b64})

    async def ws_handler(self, request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self.clients.add(ws)
        # 懒初始化会话
        if self.session is None:
            self.session = XiaozhiSession(self._reply_audio, self._log)
        try:
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                    except Exception:
                        continue
                    if data.get("type") != "xiaozhi":
                        continue
                    action = data.get("action")
                    if action == "start":
                        await self.session.start_listening()
                    elif action == "audio":
                        await self.session.send_audio_b64(data.get("data", ""))
                    elif action == "stop":
                        await self.session.stop_listening()
        finally:
            self.clients.discard(ws)
        return ws


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8010
    bridge = BridgeServer()
    app = web.Application()
    app.router.add_get("/xiaozhi", bridge.ws_handler)
    print("=" * 50)
    print("  小智语音桥接服务")
    print(f"  本地端口: {port}  (/xiaozhi)")
    print("=" * 50)
    web.run_app(app, host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
