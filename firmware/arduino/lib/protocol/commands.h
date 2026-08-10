#pragma once

// ============================================================
// 命令常量定义
// 必须与 software/raspberry_pi/car_brain/protocol/commands.py 保持一致
// 协议规格见 docs/communication_protocol.md
// ============================================================

namespace cmd {

// ---- 下行命令（大脑 -> 小脑）----
static const char* const GEAR   = "GEAR";    // 参数：-1(R倒车) 或 1-4 速度档位
static const char* const LIGHT  = "LIGHT";   // 参数：ON / OFF 前大灯
static const char* const STRIP  = "STRIP";   // 参数：模式,颜色,亮度 RGB灯带
static const char* const TURN   = "TURN";    // 参数：L / R / OFF 转向灯
static const char* const MUTE   = "MUTE";    // 参数：ON / OFF 引擎音效静音
static const char* const HORN   = "HORN";    // 参数：ON / OFF 鸣笛
static const char* const BRAKE  = "BRAKE";   // 参数：ON / OFF 制动（缓刹）
static const char* const EBRK   = "EBRK";    // 参数：ON 远程急刹（最高优先级）
static const char* const STATUS = "STATUS";  // 参数：GET 请求状态上报
static const char* const PING   = "PING";    // 心跳请求

// ---- 上行命令（小脑 -> 大脑）----
static const char* const STAT   = "STAT";    // 状态上报：速度,油门,档位,电压,温度,电流
static const char* const BTN    = "BTN";     // 按钮事件：按钮名,PRESS/RELEASE
static const char* const SEAT   = "SEAT";    // 就座 / 离座：ON / OFF
static const char* const PONG   = "PONG";    // 心跳响应
static const char* const ACK    = "ACK";     // 命令应答：OK / ERR:原因
static const char* const READY  = "READY";   // 上电就绪：协议版本

// ---- 按钮名（BTN 命令参数）----
static const char* const LIGHT_BTN = "LIGHT_BTN";  // D24 大灯开关
static const char* const MUTE_BTN  = "MUTE_BTN";   // D23 静音开关
static const char* const STRIP_BTN = "STRIP_BTN";  // D25 灯带开关
static const char* const HORN_BTN  = "HORN_BTN";   // D26 喇叭按钮
static const char* const EBRK_BTN  = "EBRK_BTN";   // D22 一键刹车
static const char* const TALK_BTN  = "TALK_BTN";   // D27 对讲按钮

}  // namespace cmd
