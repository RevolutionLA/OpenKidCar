// ============================================================
// HAL 桌面模拟实现（native 环境）
//
// 行为：
//   - 串口：stdin 读 / stdout 写（可被 Python 大脑端用管道驱动）
//   - 按钮：按时间表自动模拟按下（演示用，无需人工输入）
//   - 油门/刹车：周期变化模拟踩踏
//   - 执行器：打印到 stderr（避免污染 stdout 的协议串口）
// ============================================================

#include "hal.h"

#include <chrono>
#include <mutex>
#include <string>
#include <thread>

#include <stdio.h>

static std::mutex g_rx_mtx;
static std::string g_rx;
static std::thread g_rx_thread;

static void rx_loop() {
  int c;
  while ((c = fgetc(stdin)) != EOF) {
    std::lock_guard<std::mutex> lock(g_rx_mtx);
    g_rx.push_back((char)c);
  }
}

void hal_init(void) {
  setvbuf(stdout, NULL, _IONBF, 0);
  setvbuf(stderr, NULL, _IONBF, 0);
}

unsigned long hal_millis(void) {
  // 用时钟计数模拟时间流逝（以 100 倍速走，演示更直观）
  static unsigned long fake_ms = 0;
  static std::chrono::steady_clock::time_point last =
      std::chrono::steady_clock::now();
  auto now = std::chrono::steady_clock::now();
  unsigned long real = (unsigned long)std::chrono::duration_cast<
      std::chrono::milliseconds>(now - last).count();
  fake_ms += real * 100;  // 100 倍速
  last = now;
  return fake_ms;
}

void hal_delay(unsigned long ms) {
  std::this_thread::sleep_for(std::chrono::milliseconds(ms));
}

void hal_serial_begin(unsigned long baud) {
  (void)baud;
  g_rx_thread = std::thread(rx_loop);
}

bool hal_serial_available(void) {
  std::lock_guard<std::mutex> lock(g_rx_mtx);
  return !g_rx.empty();
}

char hal_serial_read(void) {
  std::lock_guard<std::mutex> lock(g_rx_mtx);
  if (g_rx.empty()) return '\0';
  char c = g_rx.front();
  g_rx.erase(g_rx.begin());
  return c;
}

void hal_serial_write(const char* s) {
  fputs(s, stdout);
}

void hal_serial_flush(void) {
  fflush(stdout);
}

// ---- 按钮：按时间表自动模拟（演示序列）----
// 演示序列：3s 按大灯 → 6s 静音 → 9s 灯带 → 12s 喇叭 → 15s 急刹 → 18s 对讲
static bool sim_window(unsigned long start_ms, unsigned long dur_ms) {
  unsigned long t = hal_millis();
  return t >= start_ms && t < start_ms + dur_ms;
}

bool hal_btn_light(void) { return sim_window(3000, 500); }
bool hal_btn_mute(void)  { return sim_window(6000, 500); }
bool hal_btn_strip(void) { return sim_window(9000, 500); }
bool hal_btn_horn(void)  { return sim_window(12000, 300); }
bool hal_btn_ebrk(void)  { return sim_window(15000, 800); }
bool hal_btn_talk(void)  { return sim_window(18000, 1500); }

// ---- 模拟量：周期变化模拟踩踏/采集 ----
static int ramp(int period_ms, int max) {
  return (int)(hal_millis() / 10 % (unsigned long)(period_ms)) * max / (period_ms);
}

int hal_analog_throttle(void) { return ramp(3000, 1023); }   // 3 秒一个油门循环
int hal_analog_brake(void)    { return ramp(2000, 1023); }   // 2 秒一个刹车循环
int hal_analog_seat(void)     { return hal_millis() > 1500 ? 800 : 0; }  // 1.5s 后"坐下"
int hal_analog_voltage(void)  { return 800; }   // 模拟 12V（标定后替换）
int hal_analog_temp(void)     { return 300; }   // 模拟 30℃（标定后替换）
int hal_analog_current(void)  { return 100; }   // 模拟 2A（标定后替换）

// ---- 输出：打印到 stderr（不污染 stdout 协议流）----
void hal_set_motor(int pwm) { fprintf(stderr, "[SIM] motor PWM=%d\n", pwm); }
void hal_set_steer(int angle) { fprintf(stderr, "[SIM] steer angle=%d\n", angle); }
void hal_set_headlight(bool on) { fprintf(stderr, "[SIM] headlight=%s\n", on ? "ON" : "OFF"); }
void hal_set_brake_light(uint8_t b) { fprintf(stderr, "[SIM] brake_light=%u\n", b); }
void hal_set_turn(char dir) { fprintf(stderr, "[SIM] turn=%c\n", dir); }
void hal_set_strip(int mode, uint32_t color, uint8_t brightness) {
  fprintf(stderr, "[SIM] strip mode=%d color=%06X brightness=%u\n",
          mode, color, brightness);
}

// ---- 输入：轮速（sim 端无硬件，用油门估算，供速度闭环演示）----
int hal_read_speed_kph(void) {
  int thr = hal_analog_throttle();
  // 模拟：满油门约 25km/h（4 档上限），linear 估算
  return thr * 25 / 1023;
}
