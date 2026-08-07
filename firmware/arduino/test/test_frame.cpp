// ============================================================
// 协议模块单元测试（native 环境运行：pio test -e native）
// 使用 PlatformIO 自带的 Unity 框架
// ============================================================

#include <string.h>

#include <unity.h>

#include "crc8.h"
#include "frame.h"

// ---- 固件测试钩子前向声明（src/main.cpp，UNIT_TEST 时暴露）----
extern "C" {
void test_handle_command(const char* c, const char* p);
int test_get_gear(void);
bool test_get_light(void);
int test_get_mute(void);
int test_get_strip_mode(void);
bool test_get_brake(void);
bool test_get_ebrk(void);
void test_reset(void);
}

void setUp(void) { test_reset(); }
void tearDown(void) {}

// ---- CRC8 已知值：LIGHT:ON = 0xB7（见协议文档示例）----
void test_crc8_known_value(void) {
  const char* body = "LIGHT:ON";
  uint8_t crc = crc8((const uint8_t*)body, strlen(body));
  TEST_ASSERT_EQUAL_HEX8(0xB7, crc);
}

// ---- CRC8 与 Python 端一致：GEAR:3 ----
void test_crc8_gear3(void) {
  const char* body = "GEAR:3";
  uint8_t crc = crc8((const uint8_t*)body, strlen(body));
  // 与 Python car_brain/protocol/crc8.py 对照（已在 test_protocol.py 验证）
  TEST_ASSERT_EQUAL_HEX8(0x11, crc);
}

// ---- 编码：LIGHT:ON 应生成 #LIGHT:ON;CK:B7\n ----
void test_encode_light_on(void) {
  char out[FRAME_MAX_LEN];
  size_t n = frame_encode("LIGHT", "ON", out, sizeof(out));
  TEST_ASSERT_EQUAL(16, n);  // '#' + "LIGHT:ON" + ";CK:B7\n"
  TEST_ASSERT_EQUAL_STRING("#LIGHT:ON;CK:B7\n", out);
}

// ---- 编码：无参数命令 PING ----
void test_encode_ping(void) {
  char out[FRAME_MAX_LEN];
  size_t n = frame_encode("PING", "", out, sizeof(out));
  TEST_ASSERT_EQUAL(12, n);  // '#' + "PING" + ";CK:1F\n"
  TEST_ASSERT_EQUAL_STRING("#PING;CK:1F\n", out);
}

// ---- 解码：合法帧 ----
void test_decode_valid(void) {
  const char* line = "#LIGHT:ON;CK:B7\n";
  char cmd[32], params[64];
  bool ok = frame_decode(line, cmd, sizeof(cmd), params, sizeof(params));
  TEST_ASSERT_TRUE(ok);
  TEST_ASSERT_EQUAL_STRING("LIGHT", cmd);
  TEST_ASSERT_EQUAL_STRING("ON", params);
}

// ---- 解码：无参数命令 ----
void test_decode_no_params(void) {
  const char* line = "#PING;CK:1F\n";
  char cmd[32], params[64];
  bool ok = frame_decode(line, cmd, sizeof(cmd), params, sizeof(params));
  TEST_ASSERT_TRUE(ok);
  TEST_ASSERT_EQUAL_STRING("PING", cmd);
  TEST_ASSERT_EQUAL_STRING("", params);
}

// ---- 解码：校验错误必须拒绝 ----
void test_decode_bad_checksum(void) {
  const char* line = "#LIGHT:ON;CK:00\n";  // 故意写错校验
  char cmd[32], params[64];
  bool ok = frame_decode(line, cmd, sizeof(cmd), params, sizeof(params));
  TEST_ASSERT_FALSE(ok);
}

// ---- 解码：缺帧头必须拒绝 ----
void test_decode_missing_frame_header(void) {
  const char* line = "LIGHT:ON;CK:B7\n";
  char cmd[32], params[64];
  bool ok = frame_decode(line, cmd, sizeof(cmd), params, sizeof(params));
  TEST_ASSERT_FALSE(ok);
}

// ---- 编码 + 解码往返一致 ----
void test_roundtrip(void) {
  char frame[FRAME_MAX_LEN];
  size_t n = frame_encode("STRIP", "1,FF0000,100", frame, sizeof(frame));
  TEST_ASSERT_TRUE(n > 0);

  char cmd[32], params[64];
  bool ok = frame_decode(frame, cmd, sizeof(cmd), params, sizeof(params));
  TEST_ASSERT_TRUE(ok);
  TEST_ASSERT_EQUAL_STRING("STRIP", cmd);
  TEST_ASSERT_EQUAL_STRING("1,FF0000,100", params);
}

// ---- 帧被截断 / 缺校验位：拒绝 ----
void test_decode_truncated(void) {
  const char* line = "#LIGHT:ON;CK:B7";  // 无换行（但以\0结尾，应能解）
  char cmd[32], params[64];
  bool ok = frame_decode(line, cmd, sizeof(cmd), params, sizeof(params));
  TEST_ASSERT_TRUE(ok);

  const char* bad = "#LIGHT:ON;B7\n";  // 缺 ;CK: 前缀
  ok = frame_decode(bad, cmd, sizeof(cmd), params, sizeof(params));
  TEST_ASSERT_FALSE(ok);
}

// ============================================================
// 固件命令逻辑测试（src/main.cpp 的测试钩子，UNIT_TEST 时暴露）
// 验证 handle_command 对 GEAR/LIGHT/STRIP/TURN/MUTE/EBRK 等命令的处理
// ============================================================
void test_gear_set(void) {
  test_handle_command("GEAR", "3");
  TEST_ASSERT_EQUAL_INT(3, test_get_gear());
}

void test_gear_invalid(void) {
  test_handle_command("GEAR", "5");  // 超出 1-4
  TEST_ASSERT_EQUAL_INT(2, test_get_gear());  // 保持默认
  test_handle_command("GEAR", "0");
  TEST_ASSERT_EQUAL_INT(2, test_get_gear());
}

void test_light_on_off(void) {
  test_handle_command("LIGHT", "ON");
  TEST_ASSERT_TRUE(test_get_light());
  test_handle_command("LIGHT", "OFF");
  TEST_ASSERT_FALSE(test_get_light());
}

void test_light_invalid(void) {
  test_handle_command("LIGHT", "XXX");
  TEST_ASSERT_FALSE(test_get_light());  // 无效不改变
}

void test_mute(void) {
  test_handle_command("MUTE", "ON");
  TEST_ASSERT_EQUAL_INT(1, test_get_mute());
  test_handle_command("MUTE", "OFF");
  TEST_ASSERT_EQUAL_INT(0, test_get_mute());
}

void test_strip_on(void) {
  test_handle_command("STRIP", "1,FF0000,100");
  TEST_ASSERT_EQUAL_INT(1, test_get_strip_mode());
}

void test_strip_off(void) {
  test_handle_command("STRIP", "0,FFFFFF,0");
  TEST_ASSERT_EQUAL_INT(0, test_get_strip_mode());
}

void test_brake(void) {
  test_handle_command("BRAKE", "ON");
  TEST_ASSERT_TRUE(test_get_brake());
  test_handle_command("BRAKE", "OFF");
  TEST_ASSERT_FALSE(test_get_brake());
}

void test_ebrk(void) {
  test_handle_command("EBRK", "ON");
  TEST_ASSERT_TRUE(test_get_ebrk());
  TEST_ASSERT_TRUE(test_get_brake());  // 急刹同时强制刹车
}

void test_unknown(void) {
  test_handle_command("FOO", "BAR");
  TEST_ASSERT_EQUAL_INT(2, test_get_gear());  // 不崩溃、状态不变
}

int main(void) {
  UNITY_BEGIN();
  RUN_TEST(test_crc8_known_value);
  RUN_TEST(test_crc8_gear3);
  RUN_TEST(test_encode_light_on);
  RUN_TEST(test_encode_ping);
  RUN_TEST(test_decode_valid);
  RUN_TEST(test_decode_no_params);
  RUN_TEST(test_decode_bad_checksum);
  RUN_TEST(test_decode_missing_frame_header);
  RUN_TEST(test_roundtrip);
  RUN_TEST(test_decode_truncated);
  // ---- 固件命令逻辑测试（来自 src/main.cpp 的测试钩子）----
  RUN_TEST(test_gear_set);
  RUN_TEST(test_gear_invalid);
  RUN_TEST(test_light_on_off);
  RUN_TEST(test_light_invalid);
  RUN_TEST(test_mute);
  RUN_TEST(test_strip_on);
  RUN_TEST(test_strip_off);
  RUN_TEST(test_brake);
  RUN_TEST(test_ebrk);
  RUN_TEST(test_unknown);
  return UNITY_END();
}
