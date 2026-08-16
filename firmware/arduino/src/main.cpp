// ============================================================
// 干杯一号 —— 小脑（Arduino Mega 2560）主程序
//
// 职责：
//   - 通过协议串口与大脑（树莓派）通信（docs/communication_protocol.md）
//   - 解析并执行大脑下发的命令
//   - 轮询按钮 / 踏板，边缘检测后上报大脑
//   - 定时上报车辆状态（油门 / 档位 / 电压 / 温度 / 电流）
//
// 平台无关：所有硬件访问都走 HAL（hal/hal.h）
//   native 环境 → hal_sim.cpp（桌面模拟）
//   mega2560 环境 → hal_mega.cpp（真实引脚）
// ============================================================

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "commands.h"
#include "frame.h"
#include "hal/hal.h"

// ================= 全局状态 =================
static int   g_gear = 2;          // 速度档位（1-4），默认 2 档
static bool  g_light = false;     // 前大灯
static int   g_mute = 0;          // 引擎音效静音 0/1
static int   g_steer = 90;        // 转向角度 0-180，90=直行
static int   g_strip_mode = 0;    // 灯带模式
static unsigned long g_strip_color = 0xFFFFFF;
static int   g_strip_brightness = 100;
static bool  g_brake = false;     // 制动状态
static bool  g_ebrk = false;      // 急刹状态
static bool  g_horn = false;      // 鸣笛状态

// 失联失效安全（P1-2）：超过该毫秒数未收到大脑任何命令 → 自动降速停车
static const unsigned long HEARTBEAT_TIMEOUT_MS = 3000;  // 3 秒
static unsigned long g_last_cmd_ms = 0;   // 上次收到命令的时间
static bool g_failsafe = false;           // 是否处于失效安全降速

// 档位对应的速度上限（km/h）
static const int GEAR_SPEED_MAX[] = {0, 10, 15, 20, 25};
static const int R_SPEED_MAX = 6;  // R 档倒车速度上限（km/h），慢速安全

// 上行状态上报周期
static const unsigned long STAT_INTERVAL_MS = 100;  // 10Hz

// ================= 串口收发缓冲 =================
static char g_line[FRAME_MAX_LEN];
static size_t g_line_len = 0;

// ================= 发送 =================
static void send_frame(const char* cmd, const char* params) {
  char buf[FRAME_MAX_LEN];
  size_t n = frame_encode(cmd, params ? params : "", buf, sizeof(buf));
  if (n == 0) return;
  hal_serial_write(buf);
  hal_serial_flush();
}

static void send_ack_ok(void) {
  send_frame(cmd::ACK, "OK");
}

static void send_ack_err(const char* reason) {
  char buf[32];
  snprintf(buf, sizeof(buf), "ERR:%s", reason);
  send_frame(cmd::ACK, buf);
}

// ================= 状态换算 =================
// 注意：AVR 的 int 只有 16 位，中间乘法一律用 long，防止整数溢出
// 模拟换算，接入真实传感器后需重新标定（见 docs/hardware_io_map.md）
static int adc_to_throttle_pct(void) {
  return (int)((long)hal_analog_throttle() * 100 / 1023);
}

static int gear_max_speed(void) {
  if (g_gear == -1) return R_SPEED_MAX;   // R 档
  return GEAR_SPEED_MAX[g_gear];
}

static int estimate_speed(void) {
  // 真实轮速（有符号）：km/h，倒车取负
  int speed = hal_read_speed_kph();
  int dir = (g_gear == -1) ? -1 : 1;   // R 档反向
  return speed * dir;
}

static int adc_to_voltage_x10(void) {
  // A3 分压采样，标定后替换
  return (int)((long)hal_analog_voltage() * 120 / 1023);  // 单位 0.1V
}

static int adc_to_temp(void) {
  return (int)((long)hal_analog_temp() * 100 / 1023);     // 单位 ℃（粗略）
}

static int adc_to_current_x10(void) {
  return (int)((long)hal_analog_current() * 20 / 1023);   // 单位 0.1A
}

// ================= 上报状态 =================
static void report_status(void) {
  char params[64];
  snprintf(params, sizeof(params), "%d,%d,%d,%d.%d,%d,%d.%d",
           estimate_speed(),
           adc_to_throttle_pct(),
           g_gear,
           adc_to_voltage_x10() / 10, adc_to_voltage_x10() % 10,
           adc_to_temp(),
           adc_to_current_x10() / 10, adc_to_current_x10() % 10);
  send_frame(cmd::STAT, params);
}

// ================= 命令处理（下行）=================
static void handle_command(const char* c, const char* p) {
  if (strcmp(c, cmd::PING) == 0) {
    send_frame(cmd::PONG, "");
    return;
  }
  if (strcmp(c, cmd::GEAR) == 0) {
    int v = atoi(p);
    if (!(v == -1 || (v >= 1 && v <= 4))) { send_ack_err("INVALID_ARG"); return; }  // -1=R倒车, 1-4前进
    g_gear = v;
    send_ack_ok();
    return;
  }
  if (strcmp(c, cmd::LIGHT) == 0) {
    if (strcmp(p, "ON") == 0) g_light = true;
    else if (strcmp(p, "OFF") == 0) g_light = false;
    else { send_ack_err("INVALID_ARG"); return; }
    hal_set_headlight(g_light);
    send_ack_ok();
    return;
  }
  if (strcmp(c, cmd::STRIP) == 0) {
    // 参数格式：模式,颜色RRGGBB,亮度(0-255)，如 1,FF0000,100
    int mode = -1;
    int brightness = 100;
    unsigned long color = 0xFFFFFF;
    int n = sscanf(p, "%d,%lX,%d", &mode, &color, &brightness);
    if (n >= 1 && mode >= 0 && brightness >= 0 && brightness <= 255) {
      g_strip_mode = mode;
      g_strip_color = color;
      g_strip_brightness = brightness;
      hal_set_strip(mode, (uint32_t)color, (uint8_t)brightness);
      send_ack_ok();
    } else {
      send_ack_err("INVALID_ARG");
    }
    return;
  }
  if (strcmp(c, cmd::TURN) == 0) {
    if (strcmp(p, "L") == 0) hal_set_turn('L');
    else if (strcmp(p, "R") == 0) hal_set_turn('R');
    else if (strcmp(p, "OFF") == 0) hal_set_turn(' ');
    else { send_ack_err("INVALID_ARG"); return; }
    send_ack_ok();
    return;
  }
  if (strcmp(c, cmd::STEER) == 0) {
    // 转向角度 0-180（90=直行）
    int a = atoi(p);
    if (a < 0 || a > 180) { send_ack_err("INVALID_ARG"); return; }
    g_steer = a;
    hal_set_steer(a);
    send_ack_ok();
    return;
  }
  if (strcmp(c, cmd::MUTE) == 0) {
    g_mute = (strcmp(p, "ON") == 0) ? 1 : 0;
    send_ack_ok();
    return;
  }
  if (strcmp(c, cmd::HORN) == 0) {
    bool on = (strcmp(p, "ON") == 0);
    g_horn = on;
    // 鸣笛音效由大脑播放；此处通知大脑当前喇叭状态
    send_ack_ok();
    return;
  }
  if (strcmp(c, cmd::BRAKE) == 0) {
    g_brake = (strcmp(p, "ON") == 0);
    if (g_brake) hal_set_brake_light(255);
    else if (!g_ebrk) hal_set_brake_light(0);
    send_ack_ok();
    return;
  }
  if (strcmp(c, cmd::EBRK) == 0) {
    if (strcmp(p, "OFF") == 0) {
      // 解除急刹：动力先归零，等下次油门才动，防突然窜出
      g_ebrk = false;
      g_brake = false;
      hal_set_motor(0);
      hal_set_brake_light(0);
      send_ack_ok();
    } else {
      // 最高优先级急刹：断电 + 刹车灯 + 停止动力
      g_ebrk = true;
      g_brake = true;
      hal_set_motor(0);
      hal_set_brake_light(255);
      send_ack_ok();
    }
    return;
  }
  if (strcmp(c, cmd::STATUS) == 0) {
    report_status();
    return;
  }
  send_ack_err("UNKNOWN");
}

// ================= 按钮边缘检测 =================
struct Button {
  const char* name;      // BTN 命令按钮名
  bool (*read)(void);    // HAL 读取
  bool last;             // 上一次状态
  unsigned long last_change;  // 消抖时间戳
};

#define DEBOUNCE_MS 30

static bool poll_button(Button* b) {
  bool cur = b->read();
  unsigned long now = hal_millis();
  if (cur != b->last && now - b->last_change >= DEBOUNCE_MS) {
    b->last = cur;
    b->last_change = now;
    // 仅在"按下"瞬间上报（上升沿）
    if (cur) {
      char params[32];
      snprintf(params, sizeof(params), "%s,PRESS", b->name);
      send_frame(cmd::BTN, params);
    }
    return true;
  }
  return false;
}

// ================= 油门动力输出（含档位限速闭环）=================
// 基于真实轮速（hal_read_speed_kph）的比例限速：
//   - 速度接近档位上限时线性收油门
//   - 达到上限则不再增加动力，维持微小的巡航油门保持速度
//   - 超上限（下坡等）则松油门由摩擦自然降速
static void drive_motor(void) {
  int thr = adc_to_throttle_pct();
  // 失效安全（P1-2）：超过 3 秒未收到大脑命令 → 自动停车
  if (hal_millis() - g_last_cmd_ms > HEARTBEAT_TIMEOUT_MS) {
    g_failsafe = true;
    hal_set_motor(0);
    return;
  }
  if (g_ebrk || g_brake) {
    hal_set_motor(0);
    return;
  }

  // 档位基础限速（软件上限，油门 % × 档位上限比例）
  int capped = thr * gear_max_speed() / 25;
  if (capped > 100) capped = 100;

  // 轮速闭环：用真实速度做二次限速（安全功能，防下坡/坡顶超速）
  int limit = gear_max_speed();
  int wheel = hal_read_speed_kph();       // 真实轮速 km/h（无符号）
  if (limit > 0 && wheel > 0) {
    // 剩余速度裕量比例：<0 说明已超限，>1 说明接近但未够
    float margin = (float)(limit - wheel) / (float)limit;
    if (margin <= 0.0f) {
      // 超速（如长下坡）：几乎不给动力，保持极小油门防完全失控
      capped = 0;
    } else if (margin < 0.5f && thr > capped) {
      // 接近上限：按下限的裕量比例收油门（capped 已含档位上限）
      capped = (int)(capped * (margin * 2.0f));
      if (capped < 0) capped = 0;
    }
  }

  // R 档倒车：负值（双向电调反向）
  if (g_gear == -1) capped = -capped;
  hal_set_motor(capped);
}

// ================= 入口 =================
// mega2560：Arduino 框架提供 main()，调用 setup/loop（需 C 链接）
// native  ：本文件提供 main()，自己调用 setup/loop
#ifdef ARDUINO
extern "C" {
#endif

void setup() {
  hal_init();
  hal_serial_begin(115200);
  // 上电就绪通知大脑
  hal_delay(100);  // 等待串口稳定
  send_frame(cmd::READY, "V0.3");
}

void loop() {
  static unsigned long last_stat = 0;

  // ---- 接收串口帧 ----
  while (hal_serial_available()) {
    char c = hal_serial_read();
    if (g_line_len == 0 && c != '#') continue;      // 帧同步：等帧头
    if (g_line_len >= FRAME_MAX_LEN - 1) {           // 超长：丢弃并重同步
      g_line_len = 0;
      continue;
    }
    g_line[g_line_len++] = c;
    if (c == '\n') {
      g_line[g_line_len] = '\0';
      char cmd_buf[32], params_buf[96];
      if (frame_decode(g_line, cmd_buf, sizeof(cmd_buf), params_buf, sizeof(params_buf))) {
        g_last_cmd_ms = hal_millis();   // 收到任意有效帧 = 心跳（失效安全用）
        g_failsafe = false;
        handle_command(cmd_buf, params_buf);
      }
      g_line_len = 0;
    }
  }

  // ---- 轮询按钮 ----
  static Button buttons[] = {
    {cmd::LIGHT_BTN, hal_btn_light, false, 0},
    {cmd::MUTE_BTN,  hal_btn_mute,  false, 0},
    {cmd::STRIP_BTN, hal_btn_strip, false, 0},
    {cmd::HORN_BTN,  hal_btn_horn,  false, 0},
    {cmd::EBRK_BTN,  hal_btn_ebrk,  false, 0},
    {cmd::TALK_BTN,  hal_btn_talk,  false, 0},
  };
  for (size_t i = 0; i < sizeof(buttons) / sizeof(buttons[0]); i++) {
    poll_button(&buttons[i]);
  }

  // ---- 急刹检测（本地兜底，不依赖大脑）----
  if (buttons[4].last && !g_ebrk) {
    g_ebrk = true;
    hal_set_motor(0);
    hal_set_brake_light(255);
    send_frame(cmd::EBRK, "ON");  // 通知大脑
  }

  // ---- 动力输出 ----
  drive_motor();

  // ---- 定时上报状态 ----
  unsigned long now = hal_millis();
  if (now - last_stat >= STAT_INTERVAL_MS) {
    last_stat = now;
    report_status();
  }
}

#ifdef ARDUINO
}  // extern "C"
#elif defined(UNIT_TEST)
// ============ 单元测试钩子：暴露内部状态与命令处理 ============
// pio test 时编译进测试程序，让 Unity 测试能验证固件逻辑
extern "C" {
void test_handle_command(const char* c, const char* p) { handle_command(c, p); }
int test_get_gear(void) { return g_gear; }
bool test_get_light(void) { return g_light; }
int test_get_mute(void) { return g_mute; }
int test_get_strip_mode(void) { return g_strip_mode; }
int test_get_steer(void) { return g_steer; }
bool test_get_brake(void) { return g_brake; }
bool test_get_ebrk(void) { return g_ebrk; }
void test_set_ebrk(bool v) { g_ebrk = v; }
void test_reset(void) { g_gear = 2; g_light = false; g_mute = 0;
  g_steer = 90; g_strip_mode = 0; g_brake = false; g_ebrk = false; g_horn = false; }
}
#elif !defined(UNIT_TEST)
// native 正常构建：提供 main()（pio run -e native）
// pio test 时定义 UNIT_TEST，不提供 main（由 Unity 测试框架提供）
#include <chrono>
#include <thread>

int main() {
  setup();
  for (;;) {
    loop();
    std::this_thread::sleep_for(std::chrono::milliseconds(1));
  }
  return 0;
}
#endif
