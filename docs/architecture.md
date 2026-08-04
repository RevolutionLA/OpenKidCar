# 系统架构

本文档描述 OpenKidCar 的整体系统架构。

## 总体设计

OpenKidCar 采用分层架构，思路类似真实汽车的设计：

```text
AI 智能层
Raspberry Pi
    ↓
串口通信协议 V0.1
    ↓
车辆控制层
Arduino
    ↓
电机 / 传感器 / 灯光 / 仪表
    ↓
电动车硬件平台
```

## 各层职责

### AI 智能层（Raspberry Pi）

负责：

- AI 语音识别与语音助手
- 摄像头视觉
- 高级控制逻辑
- 手机端连接
- 数据处理

### 车辆控制层（Arduino）

负责：

- 油门控制
- 电机控制
- 灯光控制
- 传感器读取
- 安全保护
- 实时控制

### 硬件执行层

包括：

- 电池系统
- 电机系统
- 电机控制器
- 车架
- 传感器
- 自定义外壳

## 通信方式

Raspberry Pi 与 Arduino 通过串口（UART）通信，消息格式见[通信协议](communication_protocol.md)。
