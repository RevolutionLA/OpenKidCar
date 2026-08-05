"""CRC-8/ATM 校验。

与 firmware/arduino/src/protocol/crc8.cpp 的实现保持一致
（多项式 0x07，初值 0x00）。
"""


def crc8(data: bytes) -> int:
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ 0x07) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc
