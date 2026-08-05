"""协议单元测试。

运行：python -m unittest discover -s tests -v
"""

import unittest

from car_brain.protocol import decode, encode
from car_brain.protocol.crc8 import crc8


class TestCRC8(unittest.TestCase):
    """CRC8 已知值 —— 与 Arduino 端 test_frame.cpp 的断言保持一致。"""

    def test_light_on(self):
        self.assertEqual(crc8(b"LIGHT:ON"), 0xB7)

    def test_ping(self):
        self.assertEqual(crc8(b"PING"), 0x1F)

    def test_gear3(self):
        self.assertEqual(crc8(b"GEAR:3"), 0x11)


class TestFrame(unittest.TestCase):
    def test_encode_light_on(self):
        self.assertEqual(encode("LIGHT", "ON"), b"#LIGHT:ON;CK:B7\n")

    def test_encode_ping(self):
        self.assertEqual(encode("PING"), b"#PING;CK:1F\n")

    def test_roundtrip(self):
        self.assertEqual(
            decode(encode("STRIP", "1,FF0000,100")),
            ("STRIP", "1,FF0000,100"),
        )

    def test_roundtrip_no_params(self):
        self.assertEqual(decode(encode("PING")), ("PING", ""))

    def test_decode_bad_checksum(self):
        self.assertIsNone(decode(b"#LIGHT:ON;CK:00\n"))

    def test_decode_no_header(self):
        self.assertIsNone(decode(b"LIGHT:ON;CK:B7\n"))

    def test_decode_corrupted_param(self):
        # 参数被篡改，CRC 对不上，必须拒绝
        self.assertIsNone(decode(b"#LIGHT:OF;CK:B7\n"))

    def test_decode_strip_crlf(self):
        # 兼容 \r\n 结尾
        self.assertEqual(decode(b"#PING;CK:1F\r\n"), ("PING", ""))


if __name__ == "__main__":
    unittest.main()
