"""串口通信层。

负责协议的物理传输：发送帧、按行接收并解析帧。
底层的 read/write 来自 pyserial 串口对象（也可注入内存模拟对象用于测试）。
"""

from .protocol.frame import decode, encode


class SerialLink:
    def __init__(self, serial_obj):
        """serial_obj：pyserial 串口对象，或实现了 read(size)/write(bytes) 的模拟对象。"""
        self.ser = serial_obj
        self._buf = b""

    def send(self, cmd: str, params: str | None = None) -> None:
        """发送一帧（自动封装 + 校验）。"""
        frame = encode(cmd, params)
        self.ser.write(frame)

    def receive(self) -> tuple[str, str] | None:
        """读取并解析一帧。

        内部按 '\\n' 切行，处理粘包/断包；校验失败或帧不完整返回 None。
        """
        while True:
            if b"\n" in self._buf:
                line, self._buf = self._buf.split(b"\n", 1)
                line += b"\n"
                return decode(line)  # 无效帧也返回 None，但已消费掉
            chunk = self.ser.read(256)
            if not chunk:
                return None  # 当前无更多数据（读超时）
            self._buf += chunk
