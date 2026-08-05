#include "frame.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "crc8.h"

size_t frame_encode(const char* cmd, const char* params, char* out, size_t max) {
  char body[FRAME_MAX_LEN];
  int n;

  if (params && params[0] != '\0')
    n = snprintf(body, sizeof(body), "%s:%s", cmd, params);
  else
    n = snprintf(body, sizeof(body), "%s", cmd);

  if (n < 0 || (size_t)n >= sizeof(body)) return 0;

  uint8_t crc = crc8((const uint8_t*)body, (size_t)n);

  char tail[16];
  int m = snprintf(tail, sizeof(tail), ";CK:%02X\n", crc);
  if (m < 0) return 0;

  size_t total = 1 + (size_t)n + (size_t)m;  // 1 = 帧头 '#'
  if (total >= max) return 0;                // 需保留结尾 \0

  out[0] = '#';
  memcpy(out + 1, body, (size_t)n);
  memcpy(out + 1 + n, tail, (size_t)m + 1);  // 含结尾 \0
  return total;
}

bool frame_decode(const char* line, char* cmd, size_t cmd_cap,
                  char* params, size_t params_cap) {
  if (!line) return false;

  size_t len = strlen(line);
  // 去掉尾部换行/回车
  while (len > 0 && (line[len - 1] == '\n' || line[len - 1] == '\r')) len--;

  if (len < 1 || line[0] != '#') return false;

  // 定位 ";CK:"
  const char* semi = strchr(line, ';');
  if (!semi || (size_t)(semi - line) >= len) return false;
  if (strncmp(semi, ";CK:", 4) != 0) return false;

  // 校验段必须是两位十六进制
  size_t ck_pos = (size_t)(semi - line) + 4;
  if (ck_pos + 2 != len) return false;

  // body = line[1 .. semi)
  size_t body_len = (size_t)(semi - line) - 1;
  char body[FRAME_MAX_LEN];
  if (body_len >= sizeof(body)) return false;
  memcpy(body, line + 1, body_len);
  body[body_len] = '\0';

  // CRC 校验
  uint8_t expect = (uint8_t)strtoul(semi + 4, NULL, 16);
  uint8_t got = crc8((const uint8_t*)body, body_len);
  if (got != expect) return false;

  // 拆分命令与参数
  const char* colon = strchr(body, ':');
  if (colon) {
    size_t cmd_len = (size_t)(colon - body);
    if (cmd_len >= cmd_cap) return false;
    memcpy(cmd, body, cmd_len);
    cmd[cmd_len] = '\0';

    size_t p_len = body_len - cmd_len - 1;
    if (p_len >= params_cap) return false;
    memcpy(params, colon + 1, p_len);
    params[p_len] = '\0';
  } else {
    if (body_len >= cmd_cap) return false;
    memcpy(cmd, body, body_len + 1);  // 含结尾 \0
    params[0] = '\0';
  }
  return true;
}
