#pragma once

#include <stddef.h>
#include <stdint.h>

// CRC-8/ATM 校验（多项式 0x07，初值 0x00）
// 与 Python 端 car_brain/protocol/crc8.py 的实现保持一致
uint8_t crc8(const uint8_t* data, size_t len);
