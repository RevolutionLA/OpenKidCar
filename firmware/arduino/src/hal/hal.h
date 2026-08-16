#pragma once

#include <stdbool.h>
#include <stdint.h>

// ============================================================
// 硬件抽象层（HAL）接口
//
// 逻辑层（main.cpp / 协议模块）只调用这里定义的函数，
// 不关心底层是真实 Arduino 还是 PC 模拟：
//   - hal_sim.cpp   桌面模拟实现（native 环境编译）
//   - hal_mega.cpp  真实引脚实现（mega2560 环境编译）
//
// 引脚分配见 docs/hardware_io_map.md
// ============================================================

// ---- 初始化 ----
void hal_init(void);

// ---- 时间（毫秒）----
unsigned long hal_millis(void);
void hal_delay(unsigned long ms);

// ---- 串口（协议专用，禁止打印日志）----
void hal_serial_begin(unsigned long baud);
bool hal_serial_available(void);   // 是否有字节可读
char hal_serial_read(void);        // 读一个字节
void hal_serial_write(const char* s);  // 写字符串
void hal_serial_flush(void);

// ---- 输入：按钮（按下返回 true）----
bool hal_btn_light(void);   // D24 大灯开关
bool hal_btn_mute(void);    // D23 静音开关
bool hal_btn_strip(void);   // D25 灯带开关
bool hal_btn_horn(void);    // D26 喇叭按钮
bool hal_btn_ebrk(void);    // D22 一键刹车（自锁）
bool hal_btn_talk(void);    // D27 对讲按钮

// ---- 输入：模拟量（0-1023）----
int hal_analog_throttle(void);  // A0 油门踏板
int hal_analog_brake(void);     // A1 刹车踏板
int hal_analog_seat(void);      // A2 坐垫压力（就座检测）
int hal_analog_voltage(void);   // A3 电池电压（分压采样）
int hal_analog_temp(void);      // A4 电池仓温度（NTC）
int hal_analog_current(void);   // A5 电机电流

// ---- 输出：执行器 ----
void hal_set_motor(int pwm);                // D9 电机油门 -100..100（负=倒车，双向电调）
void hal_set_steer(int angle);              // D10 转向舵机 0-180（90=直行）
void hal_set_headlight(bool on);            // D2 前大灯
void hal_set_brake_light(uint8_t b);        // D3 刹车灯 0-255
void hal_set_turn(char dir);                // D4/D5 转向灯 'L'/'R'/' '
void hal_set_strip(int mode, uint32_t color, uint8_t brightness);  // D11 灯带

// ---- 输入：轮速（真实速度闭环用）----
int hal_read_speed_kph(void);               // 轮速传感器实测速度 km/h（有符号，负=倒车）
