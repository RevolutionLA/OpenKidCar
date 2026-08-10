# 硬件部署指导书（拿到硬件照着做）

> 目的：当你拿到树莓派、Arduino、电机等硬件后，**照着这份手册一步步做**，就能把数字孪生里验证的功能跑在真实硬件上。
> 配套：引脚分配见 [hardware_io_map.md](hardware_io_map.md)，协议见 [communication_protocol.md](communication_protocol.md)。

---

## 0. 需要准备的硬件清单

| 硬件 | 规格 | 用途 |
|---|---|---|
| 树莓派 4B | 4GB+ | 大脑：决策/干杯助手/双端服务 |
| Arduino Mega 2560 | 标准版 | 小脑：实时执行 |
| 电池 | 12V | 整车供电 |
| 电调 + 电机 | — | 驱动 |
| DC-DC 降压 | 12V→5V/3A | 给树莓派/Arduino 供电 |
| USB 麦克风 | 16kHz+ | 干杯助手收音 |
| USB 音箱/声卡 | — | 干杯助手播放回复（与音效隔离） |
| 按键 ×N | 轻触/自锁 | 大灯/静音/灯带/喇叭/急刹/对讲 |
| 踏板传感器 ×2 | 霍尔/电位器 | 油门/刹车 |
| 杜邦线 + 电平转换模块 | — | 树莓派↔Arduino 串口 |
| 4G/GPS 模块 | USB，SIM7600 等 | 定位/远程（P0，可后加） |

---

## 1. 连线（照着接线）

### 1.1 树莓派 ↔ Arduino 通信（UART）

```
树莓派 4B                   电平转换模块                Arduino Mega
GPIO14 (TXD) ────────────►  TTL(3.3V→5V)  ───────────► D19 (RX1)
GPIO15 (RXD) ◄────────────  TTL(5V→3.3V)  ◄─────────── D18 (TX1)
GND ──────────────────────► 共地 ──────────────────────► GND
```

⚠️ **必须用双向电平转换模块**（Arduino 5V → 树莓派 3.3V 方向），否则烧毁树莓派 GPIO。

### 1.2 Arduino 执行器（输出）

| Arduino 引脚 | 接 | 说明 |
|---|---|---|
| D9 | 电调信号线 | 电机油门 PWM |
| D10 | 舵机/转向电机 | 转向 |
| D2 | 大灯（经继电器/高边驱动） | 前大灯 |
| D3 | 刹车灯 | 亮度可调 |
| D4 | 左转向灯 | 经驱动 |
| D5 | 右转向灯 | 经驱动 |
| D11 | WS2812B 灯带数据线 | RGB 灯带 |

### 1.3 Arduino 传感器/按钮（输入）

| Arduino 引脚 | 接 | 说明 |
|---|---|---|
| A0 | 油门踏板 | 模拟 0-1023 |
| A1 | 刹车踏板 | 模拟 0-1023 |
| A2 | 坐垫压力 | 就座检测 |
| A3 | 电池电压（分压） | 电量 |
| A4 | 温度（NTC） | 过热保护 |
| A5 | 电机电流 | 过流保护 |
| D22 | 急刹按钮 | 最高优先级 |
| D23 | 静音开关 | |
| D24 | 大灯开关 | |
| D25 | 灯带开关 | |
| D26 | 喇叭按钮 | |
| D27 | 对讲按钮 | |

### 1.4 电源

```
电池 12V ─┬─► 电调 ─► 电机
           └─► DC-DC 5V ─► 树莓派 + Arduino
```

### 1.5 干杯助手音频（独立于音效）

```
USB 麦克风 ─► 树莓派 USB（干杯助手收音）
USB 音箱/声卡 ─► 树莓派 USB（干杯助手播放回复）
3.5mm 音频 ─► 功放 ─► 扬声器（引擎轰鸣/鸣笛/对讲）
```

> **对话与音效必须用不同声卡**，物理隔离最稳，否则引擎声会被麦克风采集影响识别。

---

## 2. 下载与安装（树莓派）

### 2.1 树莓派系统

```bash
# 推荐 Raspberry Pi OS (Bookworm, 64位)
# 装好后启用串口：
sudo raspi-config
# → Interface Options → Serial Port → "登录 shell"选 No, "串口硬件"选 Yes
```

### 2.2 安装 Python 依赖（大脑）

```bash
cd ~/OpenKidCar/software/raspberry_pi
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
# vosk 模型（干杯助手替代了它，可跳过；如需离线指令控制再装）
# mkdir -p ~/vosk-model-small-cn-0.22 && 下载解压到该目录
```

### 2.3 安装干杯助手（py-xiaozhi）

```bash
git clone https://github.com/huangjunsen0406/py-xiaozhi.git
cd py-xiaozhi
python3 -m venv .venv          # 树莓派默认 Python 3.11 ✅
.venv/bin/pip install -r requirements.txt
# Opus 库：项目内置 libs/libopus/linux/arm64/libopus.so，无需手动装
```

---

## 3. 烧录小脑固件（Arduino）

```bash
cd ~/OpenKidCar/firmware/arduino
# 用 PlatformIO（VSCode 插件或 CLI）
pio run -e mega2560              # 编译
pio run -e mega2560 -t upload    # 烧录（USB 连 Arduino）
# 也可用 Arduino IDE：打开 src/main.cpp，选板子 Mega 2560，点上传
```

烧录成功：串口监视器应能看到小脑就绪（READY V0.3）。

---

## 4. 启动真实硬件系统

### 4.1 启动干杯助手桥接

```bash
cd ~/py-xiaozhi
.venv/bin/python main.py --mode cli   # 首次需激活：访问 xiaozhi.me 输验证码
```

### 4.2 启动数字孪生（连真实 Arduino）

```bash
cd ~/OpenKidCar/software/raspberry_pi
# 必须先设家长端访问密码（安全）：未设密码会拒绝启动
export OPENKIDCAR_PASSWORD=你的密码
.venv/bin/python digital_twin/backend/twin_server.py 8000 8001 \
    --real-serial /dev/ttyACM0    # 树莓派上 Arduino 通常是 /dev/ttyACM0
# 小车端 http://localhost:8000（仅本机）；家长端 http://<树莓派IP>:8001（需密码登录）
```

> 🔐 **安全**：家长端 8001 需输入密码登录（session 鉴权）；小车端 8000 仅监听本机。
> 真实硬件模式已支持（`--real-serial`），见第 6 节。

---

## 5. 验证清单（按顺序测）

| # | 测试 | 预期 | 命令/操作 |
|---|---|---|---|
| 1 | 小脑就绪 | 日志"小脑就绪 (V0.3)" | 烧录后串口监视器 |
| 2 | 串口通信 | 大脑收到 PONG | 启动 twin_server 看日志 |
| 3 | 大灯开关 | D2 灯亮/灭 | 网页点"大灯" |
| 4 | 油门 | D9 PWM 变化、速度上升 | 网页推油门 |
| 5 | 急刹 | D22 触发、停车 | 按急刹按钮/网页急刹 |
| 6 | 干杯助手对话 | 语音回复 | 按住"干杯助手"说话 |
| 7 | 干杯助手控制车 | 说"打开大灯"→灯亮 | 语音命令 |
| 8 | 家长端 | GPS/电量/对讲/视频 | 手机访问 :8001 |

---

## 6. 待开发：真实串口模式（数字孪生接 Arduino）

当前 `twin_server.py` 硬编码 `CerebellumSim`（模拟小脑）。接真实 Arduino 需加启动参数：

```python
# twin_server.py 改动思路（约 20 行）
# 1. 加参数 --real-serial /dev/ttyACM0
# 2. 有该参数时：
#    from car_brain.app import SerialPort
#    self.ceb = None  # 不再用 CerebellumSim
#    self.brain = Brain(SerialLink(SerialPort(port, 115200)))
# 3. 状态快照改从大脑维护的状态读（speed 由 Arduino STAT 上报解析）
# 4. GPS/电量改为从 Arduino 上报 / 真实 GPS 模块读
```

> 其余代码（前端、协议、大脑、干杯助手）完全复用，因为当初就是按"协议驱动 + HAL 抽象"设计的。

---

## 7. 常见问题

- **树莓派收不到 Arduino 数据**：检查电平转换、波特率 115200、`/dev/ttyACM0` 是否存在（`ls /dev/tty*`）
- **干杯助手没声音**：检查 USB 麦克风/音箱被系统识别（`arecord -l` / `aplay -l`）
- **引擎声干扰对话**：确认对话走 USB 声卡、音效走 3.5mm，两块独立
- **烧录失败**：Arduino 需要先拔掉树莓派串口连线再烧录（串口占用冲突）

---

*OpenKidCar · 干杯一号 · 拿到硬件照着做*
