"""协议帧封装 / 解析。

帧格式：#命令:参数;CK:XX\n
  - 最大帧长 128 字节
  - CRC8 校验覆盖"命令:参数"（不含 #、;CK:XX 本身）
规格见 docs/communication_protocol.md
"""

from .crc8 import crc8

FRAME_MAX_LEN = 128


def encode(cmd: str, params: str | None = None) -> bytes:
    """编码一帧，返回字节串（含结尾 \\n）。"""
    body = f"{cmd}:{params}" if params else cmd
    body_b = body.encode("ascii")
    if len(body_b) + 8 > FRAME_MAX_LEN:  # 帧头+校验段预留空间
        raise ValueError(f"frame too long: {body}")
    ck = crc8(body_b)
    return f"#{body};CK:{ck:02X}\n".encode("ascii")


def decode(line: bytes) -> tuple[str, str] | None:
    """解析一帧，返回 (命令, 参数)。校验失败或格式错误返回 None。

    line 可以带结尾 \\n（多余空白自动去除）。
    """
    line = line.strip(b"\r\n")
    if not line.startswith(b"#"):
        return None

    # 定位 ";CK:" 校验段
    m = line.find(b";CK:")
    if m < 0:
        return None

    body = line[1:m]
    ck_hex = line[m + 4:m + 6]
    try:
        expect = int(ck_hex, 16)
    except ValueError:
        return None

    if crc8(body) != expect:
        return None

    body_s = body.decode("ascii")
    if ":" in body_s:
        cmd, params = body_s.split(":", 1)
    else:
        cmd, params = body_s, ""
    return cmd, params
