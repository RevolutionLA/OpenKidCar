# 大脑工程（Raspberry Pi / 桌面）

干杯一号的大脑 —— 负责 AI 交互、决策、与小脑通信。

> **跨平台**：Python 代码在 Windows 开发与树莓派（Linux）部署运行同一套代码。

## 架构

```
car_brain/
├── protocol/          协议模块
│   ├── crc8.py        CRC8 校验（与 Arduino 端一致）
│   ├── commands.py    命令常量（与 Arduino 端 commands.h 保持一致）
│   └── frame.py       帧封装 / 解析
├── serial_link.py     串口通信层（帧收发）
├── brain.py           大脑状态机（状态视图 / 心跳 / 按钮决策）
└── app.py             CLI 入口
tests/
├── test_protocol.py   协议单元测试
└── test_brain_loop.py 大脑↔小脑内存联调测试
```

## 安装

```bash
pip install -r requirements.txt   # 需要 pyserial
```

## 运行测试

```bash
# 协议单元测试 + 大脑↔小脑联调测试
python -m unittest discover -s tests -v
```

`test_brain_loop.py` 用两个线程 + 内存管道模拟"大脑 ↔ 小脑"完整对话，
无需任何硬件即可验证协议闭环。

## 运行演示

### 方式一：连接真实/虚拟串口

```bash
# Windows 真实串口
python -m car_brain.app --port COM3 --demo

# Linux / 树莓派
python -m car_brain.app --port /dev/ttyAMA0 --demo
```

### 方式二：直接驱动 native 小脑（无需串口，推荐联调）

先编译小脑 native 程序（见 [firmware/arduino/README.md](../../firmware/arduino/README.md)），
然后让大脑通过 stdin/stdout 管道驱动它：

```bash
python -m car_brain.app --native ../firmware/arduino/.pio/build/native/program.exe --demo
```

> 这样在 Windows 上无需安装 com0com 虚拟串口，也能看到完整的两端对话。

## 目录规划（后续迭代）

- `voice/` —— 语音唤醒"干杯出来"（vosk 离线识别）
- `audio/` —— 引擎音效合成 + 音频管理
- `cloud/` —— 4G 通信 / MQTT / APP 对接
- `gps/` —— 定位上报
