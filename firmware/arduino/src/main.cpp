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
static int   g_strip_mode = 0;    // 灯带模式
static unsigned long g_strip_color = 0xFFFFFF;
static int   g_strip_brightness = 100;
static bool  g_brake = false;     // 制动状态
static bool  g_ebrk = false;      // 急刹状态
static bool  g_horn = false;      // 鸣笛状态

// 档位对应的速度上限（km/h）
static const int GEAR_SPEED_MAX[] = {0, 10, 15, 20, 25};

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

static int estimate_speed(void) {
  // 无轮速传感器前，用油门 × 档位上限估算
  int thr = adc_to_throttle_pct();
  long v = (long)thr * GEAR_SPEED_MAX[g_gear] * 70 / 10000;
  return (int)v;
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
    if (v < 1 || v > 4) { send_ack_err("INVALID_ARG"); return; }
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
    int mode = atoi(p);
    if (mode < 0) { send_ack_err("INVALID_ARG"); return; }
    g_strip_mode = mode;
    // TODO: 解析颜色/亮度参数（当前仅演示模式切换）
    hal_set_strip(g_strip_mode, g_strip_color, g_strip_brightness);
    send_ack_ok();
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
    // 最高优先级急刹：断电 + 刹车灯 + 停止动力
    g_ebrk = true;
    g_brake = true;
    hal_set_motor(0);
    hal_set_brake_light(255);
    send_ack_ok();
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

// ================= 油门动力输出 =================
static void drive_motor(void) {
  int thr = adc_to_throttle_pct();
  if (g_ebrk || g_brake) {
    hal_set_motor(0);
    return;
  }
  // 档位限速：油门百分比 × 档位上限比例
  int capped = thr * GEAR_SPEED_MAX[g_gear] / 25;
  if (capped > 100) capped = 100;
  hal_set_motor((uint8_t)capped);
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
