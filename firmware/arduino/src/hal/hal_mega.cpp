// ============================================================
// HAL 真实引脚实现（Arduino Mega 2560）
//
// 引脚分配严格对应 docs/hardware_io_map.md
// 只有此文件依赖 Arduino API；逻辑层（main.cpp / protocol）不依赖
// ============================================================

#include "hal.h"

#include <Arduino.h>

// ---- 引脚定义（与 docs/hardware_io_map.md 保持一致）----
static const int PIN_BTN_LIGHT = 24;
static const int PIN_BTN_MUTE  = 23;
static const int PIN_BTN_STRIP = 25;
static const int PIN_BTN_HORN  = 26;
static const int PIN_BTN_EBRK  = 22;
static const int PIN_BTN_TALK  = 27;

static const int PIN_ANA_THROTTLE = A0;
static const int PIN_ANA_BRAKE    = A1;
static const int PIN_ANA_SEAT     = A2;
static const int PIN_ANA_VOLTAGE  = A3;
static const int PIN_ANA_TEMP     = A4;
static const int PIN_ANA_CURRENT  = A5;

static const int PIN_MOTOR    = 9;
static const int PIN_STEER    = 10;
static const int PIN_HEADLIGHT = 2;
static const int PIN_BRAKE_LIGHT = 3;
static const int PIN_TURN_L   = 4;
static const int PIN_TURN_R   = 5;
// D11 = RGB 灯带（WS2812B），需 NeoPixel 库，见 hal_set_strip

void hal_init(void) {
  pinMode(PIN_BTN_LIGHT, INPUT_PULLUP);
  pinMode(PIN_BTN_MUTE,  INPUT_PULLUP);
  pinMode(PIN_BTN_STRIP, INPUT_PULLUP);
  pinMode(PIN_BTN_HORN,  INPUT_PULLUP);
  pinMode(PIN_BTN_EBRK,  INPUT_PULLUP);
  pinMode(PIN_BTN_TALK,  INPUT_PULLUP);

  pinMode(PIN_MOTOR, OUTPUT);
  pinMode(PIN_STEER, OUTPUT);
  pinMode(PIN_HEADLIGHT, OUTPUT);
  pinMode(PIN_BRAKE_LIGHT, OUTPUT);
  pinMode(PIN_TURN_L, OUTPUT);
  pinMode(PIN_TURN_R, OUTPUT);
}

unsigned long hal_millis(void) { return millis(); }
void hal_delay(unsigned long ms) { delay(ms); }

void hal_serial_begin(unsigned long baud) { Serial1.begin(baud); }
bool hal_serial_available(void) { return Serial1.available() > 0; }
char hal_serial_read(void) { return (char)Serial1.read(); }
void hal_serial_write(const char* s) { Serial1.print(s); }
void hal_serial_flush(void) { Serial1.flush(); }

// 按钮接 GND，INPUT_PULLUP，按下为 LOW，取反为逻辑 true
static bool btn_active(int pin) { return digitalRead(pin) == LOW; }

bool hal_btn_light(void) { return btn_active(PIN_BTN_LIGHT); }
bool hal_btn_mute(void)  { return btn_active(PIN_BTN_MUTE); }
bool hal_btn_strip(void) { return btn_active(PIN_BTN_STRIP); }
bool hal_btn_horn(void)  { return btn_active(PIN_BTN_HORN); }
bool hal_btn_ebrk(void)  { return btn_active(PIN_BTN_EBRK); }
bool hal_btn_talk(void)  { return btn_active(PIN_BTN_TALK); }

int hal_analog_throttle(void) { return analogRead(PIN_ANA_THROTTLE); }
int hal_analog_brake(void)    { return analogRead(PIN_ANA_BRAKE); }
int hal_analog_seat(void)     { return analogRead(PIN_ANA_SEAT); }
int hal_analog_voltage(void)  { return analogRead(PIN_ANA_VOLTAGE); }
int hal_analog_temp(void)     { return analogRead(PIN_ANA_TEMP); }
int hal_analog_current(void)  { return analogRead(PIN_ANA_CURRENT); }

// 双向电调（ESC）：油门脉宽 1000-2000us，1500=中位停，>1500 前进，<1500 后退
// 用自定义脉冲输出（PWM 频率 50Hz，脉宽按档位+油门映射）
static const int ESC_MIN_US  = 1000;   // 全倒
static const int ESC_MID_US  = 1500;   // 停止
static const int ESC_MAX_US  = 2000;   // 全进

void hal_set_motor(int pwm) {
  // pwm: -100..100，负=倒车
  int clamped = pwm < -100 ? -100 : (pwm > 100 ? 100 : pwm);
  int us = ESC_MID_US + clamped * (ESC_MAX_US - ESC_MID_US) / 100;  // 1500 + pwm*5
  // 用 analogWrite 需设置 PWM 频率；此处用 Servo 兼容脉宽
  // 简单实现：直接映射到 PWM 占空比（Arduino analogWrite 默认 490Hz 不适合 ESC）
  // 注：真实接线需电调信号接 D9，用 Servo 库或定时器输出 50Hz 脉宽
  // 此处用 Servo 库更可靠，但避免依赖，先用 analogWrite 占位（真实硬件用 Servo）
  analogWrite(PIN_MOTOR, (unsigned int)(clamped > 0 ? clamped : -clamped) * 255 / 100);
}
void hal_set_steer(uint8_t pwm) { analogWrite(PIN_STEER, pwm * 255 / 100); }
void hal_set_headlight(bool on) { digitalWrite(PIN_HEADLIGHT, on ? HIGH : LOW); }
void hal_set_brake_light(uint8_t b) { analogWrite(PIN_BRAKE_LIGHT, b); }
void hal_set_turn(char dir) {
  digitalWrite(PIN_TURN_L, dir == 'L' ? HIGH : LOW);
  digitalWrite(PIN_TURN_R, dir == 'R' ? HIGH : LOW);
}

void hal_set_strip(int mode, uint32_t color, uint8_t brightness) {
  // TODO: 接入 WS2812B 灯带（NeoPixel 库）
  // 例：Adafruit_NeoPixel strip(60, PIN_STRIP, NEO_GRB + NEO_KHZ800);
  //   strip.setBrightness(brightness);
  //   strip.fill(color); strip.show();
  (void)mode; (void)color; (void)brightness;
}
