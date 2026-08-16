// ============================================================
// HAL 真实引脚实现（Arduino Mega 2560）
//
// 引脚分配严格对应 docs/hardware_io_map.md
// 只有此文件依赖 Arduino API；逻辑层（main.cpp / protocol）不依赖
//
// 动力/转向用 Servo 库输出标准脉宽：
//   - D9  电调（ESC）：50Hz，1000-2000us，1500=停
//   - D10 转向舵机：50Hz，0-180° 标准舵机角度
// 轮速用硬件外中断统计脉冲（Hall / 编码器），见 hal_read_speed_kph
// ============================================================

#include "hal.h"

#include <Arduino.h>
#include <Servo.h>

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
static const int PIN_WHEELSPEED = 21;   // 轮速传感器（Hall/编码器），外部中断 INT2

// ---- 电机电调 + 转向舵机 ----
static Servo g_esc;      // D9 电调（双向，标准 1000-2000us 脉宽）
static Servo g_steer;    // D10 转向舵机（标准 0-180°）

// ESC 脉宽范围（双向电调）：1000=全倒 1500=停 2000=全进
static const int ESC_NEUTRAL_US = 1500;
static const int ESC_RANGE_US   = 500;   // 每方向 ±500us

// ---- 轮速脉冲统计（外部中断）----
static volatile unsigned long g_wheeltick = 0;   // 霍尔脉冲计数
static const int WHEEL_TICKS_PER_REV = 4;        // 每圈脉冲数（霍尔 1 磁铁通常 1-4，可调）
static const float WHEEL_CIRCUM_M = 1.118f;      // 14 寸轮周长 ≈ π×0.356m

void wheel_pulse_isr(void) { g_wheeltick++; }

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

  pinMode(PIN_WHEELSPEED, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(PIN_WHEELSPEED), wheel_pulse_isr, FALLING);

  // 舵机 + 电调引脚共用 Timer（Mega 可用，多定时器）
  g_steer.attach(PIN_STEER, 1000, 2000);
  g_esc.attach(PIN_MOTOR, 1000, 2000);
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

// 电机：-100..100 → 1000-2000us（1500 停）。负=倒车。
void hal_set_motor(int pwm) {
  int clamped = pwm < -100 ? -100 : (pwm > 100 ? 100 : pwm);
  if (clamped == 0) {
    g_esc.writeMicroseconds(ESC_NEUTRAL_US);   // 静态：停
  } else {
    int us = ESC_NEUTRAL_US + clamped * ESC_RANGE_US / 100;
    g_esc.writeMicroseconds(us);
  }
}

// 转向：0-180°（90 = 直行）。舵机正装，角度直接写。
void hal_set_steer(int angle) {
  int a = angle < 0 ? 0 : (angle > 180 ? 180 : angle);
  g_steer.write(a);
}

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

// 轮速：统计霍尔脉冲 → 换算速度 km/h
// 注意：此实现假设 pulse 来自轮轴磁铁；实际触发频率/周期适配需按传感器现场标定
int hal_read_speed_kph(void) {
  static unsigned long last_ms = 0;
  static unsigned long last_tick = 0;
  static int last_speed = 0;
  unsigned long now_ms = hal_millis();
  if (now_ms - last_ms < 50) return last_speed;   // 500ms 采样窗，返回上次
  unsigned long dt_ms = now_ms - last_ms;
  unsigned long d_tick = g_wheeltick - last_tick;
  g_wheeltick = 0;  // 滚动清零
  last_ms = now_ms; last_tick = 0;
  if (dt_ms == 0 || d_tick == 0) { last_speed = 0; return 0; }
  // 每秒转数 = 每秒脉冲 / 每圈脉冲
  float rev_per_s = (float)d_tick * (1000.0f / dt_ms) / WHEEL_TICKS_PER_REV;
  float mps = rev_per_s * WHEEL_CIRCUM_M;
  last_speed = (int)(mps * 3.6f);   // m/s → km/h
  if (last_speed < 0) last_speed = 0;   // 方向看档位，这里只给大小
  return last_speed;
}
