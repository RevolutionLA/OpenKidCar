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

## 🎙️ 语音控制（vosk 离线识别）

对着麦克风说 **"干杯出来"** 唤醒，再说指令；也可一句话连说（"干杯出来开灯"）。

支持指令：打开大灯 / 关灯 / 静音 / 取消静音 / 一至四档 / 急刹。

### 准备（一次性）

```bash
# 1. 创建 Python 3.13 虚拟环境（系统 3.14 对语音库支持可能不全）
py -3.13 -m venv .venv

# 2. 安装依赖
.venv\Scripts\python.exe -m pip install -r requirements.txt

# 3. 下载 vosk 中文模型（~42MB），解压到用户目录：
#    https://alphacephei.com/vosk/models/vosk-model-small-cn-0.22.zip
#    解压后目录应为 ~/vosk-model-small-cn-0.22
#    也可设置环境变量 VOSK_MODEL 指向模型目录
```

### 运行语音控制

```bash
.venv\Scripts\python.exe -m car_brain.app --native <小脑exe路径> --voice --seconds 120
```

> 需要电脑有麦克风。语音识别是离线的，不联网。Windows 下会说"我在，请说指令"作为语音反馈。

### 如何添加 / 删除指令

指令的"名单"在 `car_brain/voice.py` 的 **`COMMAND_RULES`** 表（每行 = 一组同义词 + 指令）：

```python
COMMAND_RULES = (
    (("打开大灯", "开大灯", "开灯", "亮灯"), ("light", "on")),  # 同义词 → 指令
    (("刹车", "急刹", "停车"), ("ebrk", None)),
)
```

- **加同义词**：往对应行的关键词元组里加词即可
- **新增指令、复用已有动作**：加一行，指令名用已有的（如 `strip`）
- **新增全新动作**：加一行 + 在 `car_brain/app.py` 的 `on_voice_command` 里加处理分支；若需要新的协议命令，再给 `car_brain/brain.py` 加方法
- **删除指令**：直接删掉对应行

### 更换语音音色

设置环境变量 `TTS_VOICE`（默认 `zh-CN-XiaoxiaoNeural` 晓晓）：

```bash
set TTS_VOICE=zh-CN-YunxiNeural   # 云希（男声）
set TTS_VOICE=zh-CN-XiaoyiNeural  # 晓伊（女声）
```

可选项：`XiaoxiaoNeural`(晓晓) / `YunxiNeural`(云希) / `YunyangNeural`(云扬) / `XiaoyiNeural`(晓伊)。

## 目录规划（后续迭代）

- `audio/` —— 引擎音效合成 + 音频管理
- `cloud/` —— 4G 通信 / MQTT / APP 对接
- `gps/` —— 定位上报
