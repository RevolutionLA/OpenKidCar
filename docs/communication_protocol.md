# 通信协议 V0.1

本文档定义 OpenKidCar 各模块之间的串口通信协议。

## 消息格式

协议采用文本行格式，每条消息以换行结尾：

```text
命令:参数
```

示例：

```text
LIGHT:ON
LIGHT:OFF
SPEED:30
```

## Raspberry Pi -> Arduino（下行指令）

| 指令 | 含义 | 示例 |
| --- | --- | --- |
| `LIGHT:ON` | 打开车灯 | `LIGHT:ON` |
| `LIGHT:OFF` | 关闭车灯 | `LIGHT:OFF` |
| `SPEED:30` | 设置速度限制 | `SPEED:30` |
| `HORN:ON` | 鸣笛 | `HORN:ON` |
| `HORN:OFF` | 停止鸣笛 | `HORN:OFF` |
| `STATUS:GET` | 请求车辆状态 | `STATUS:GET` |

## Arduino -> Raspberry Pi（上行状态）

| 消息 | 含义 | 示例 |
| --- | --- | --- |
| `BATTERY:24.5` | 电池电压 | `BATTERY:24.5` |
| `MODE:READY` | 当前模式 | `MODE:READY` |
| `SENSOR:FRONT:OK` | 传感器状态 | `SENSOR:FRONT:OK` |

## 响应与错误

- 收到未知指令时回复：`ERROR:UNKNOWN_COMMAND`
- 参数非法时回复：`ERROR:INVALID_ARGUMENT`

## 变更记录

V0.1 为初始版本，后续版本会在这里追加变更说明。
