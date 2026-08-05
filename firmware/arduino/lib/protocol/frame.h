#pragma once

#include <stdbool.h>
#include <stddef.h>

// ============================================================
// 协议帧封装 / 解析（纯 C++，不依赖 Arduino API）
//
// 帧格式：#命令:参数;CK:XX\n
//   - 最大帧长 128 字节
//   - CRC8 校验覆盖"命令:参数"（不含 #、;CK:XX 本身）
// 规格见 docs/communication_protocol.md
// ============================================================

#define FRAME_MAX_LEN 128

// 编码一帧：生成 "#cmd[:params];CK:XX\n"
//   cmd    命令名（如 "LIGHT"）
//   params 参数（可传空字符串 ""）
//   out    输出缓冲区
//   max    out 的容量
// 返回帧长度（不含结尾 \0）；失败返回 0
size_t frame_encode(const char* cmd, const char* params, char* out, size_t max);

// 解析一帧：校验帧头与 CRC8，拆分命令与参数
//   line        输入行（以 '\n' 或 '\0' 结尾均可）
//   cmd         输出命令缓冲区
//   cmd_cap     cmd 容量
//   params      输出参数缓冲区（无参数时为空串）
//   params_cap  params 容量
// 校验通过返回 true；否则返回 false
bool frame_decode(const char* line, char* cmd, size_t cmd_cap,
                  char* params, size_t params_cap);
