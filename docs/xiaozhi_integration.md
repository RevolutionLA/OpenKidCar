# 小智语音助手集成方案

> 目标：小孩按车上的**语音对话按钮**，就能和小智 AI 语音助手对话（连小智官方服务器）。
> 不需要语音唤醒词 —— 按一下按钮开始对话，再按一下结束。

---

## 1. 选型结论

| 项 | 选择 | 理由 |
|---|---|---|
| **客户端** | `py-xiaozhi`（Python） | Python 生态（与大脑同语言）、**明确支持树莓派**、**GPIO 物理按钮触发**、CLI 简单、MIT 开源 |
| **服务端** | **小智官方服务器** | 免自建，部署最省事 |
| 不用 xiaozhi-esp32 | — | 它是 ESP32 固件，不能烧树莓派 |
| 不用 xiaozhi-linux | — | 只支持 NXP/全志等定制板，不支持树莓派 |

参考项目：
- 客户端：[huangjunsen0406/py-xiaozhi](https://github.com/huangjunsen0406/py-xiaozhi)
- 协议来源：[78/xiaozhi-esp32](https://github.com/78/xiaozhi-esp32)

---

## 2. 系统架构

```
┌─────────────────────────── 车上 · 树莓派（大脑） ───────────────────────────┐
│                                                                            │
│  [语音按钮]──GPIO──► py-xiaozhi 客户端（独立进程，Python）                     │
│                         │                                                  │
│                    USB 麦克风（收音）                                        │
│                    USB 音箱（播放回复）      ◄── 与引擎音效完全独立            │
│                         │                                                  │
│                     WebSocket（WSS）                                       │
└─────────────────────────┼──────────────────────────────────────────────────┘
                          ▼
              ┌─────────────────────┐
              │  小智官方服务器       │
              │  ASR 识别 → LLM 对话  │
              │  → TTS 合成回复       │
              └─────────────────────┘
```

**对话链路**：按按钮 → py-xiaozhi 开始录音（USB 麦克风）→ 音频流发小智官方服务器 → 服务器 ASR+LLM+TTS → 回复音频回传 → USB 音箱播放 → 再按按钮结束。

---

## 3. 音频 IO 规划（对话与音效分离）

对话音频（py-xiaozhi）和引擎轰鸣/鸣笛**必须用不同的设备**，避免互相干扰：

| 用途 | 设备 | 占用 | 说明 |
|---|---|---|---|
| **小智对话** | USB 麦克风 + USB 音箱（USB 声卡） | 独立 USB 声卡 | py-xiaozhi 专用，16kHz 采样 |
| **引擎轰鸣 / 鸣笛** | 独立扬声器 | 树莓派 3.5mm 音频输出，或另一块声卡 | 由大脑音效系统驱动，与对话通道隔离 |

> **为什么分离**：引擎声是"持续/频繁"的环境音，对话是"清晰人声" —— 混在同一音箱会让小智听不清、小孩听不清回复。用两块声卡物理隔离最稳妥。

---

## 4. 按钮接入（方式 A：GPIO 直连树莓派）

**按钮不走小脑（Arduino）** —— 它是"语音对话触发"，不是汽车控制信号，直接接树莓派 GPIO，由 py-xiaozhi 的 GPIO 模式监听：

```
按钮 ──► 树莓派 GPIO（如 GPIO17，接上拉电阻）
          py-xiaozhi GPIO 模式：按下 → 开始对话，再按 → 结束
```

- 好处：不依赖小脑、不依赖大脑协议，独立简单，未来实体机也不需走小脑
- 接线：按钮一端接 GPIO，另一端接 GND（内部上拉）

---

## 5. 硬件清单

| 硬件 | 规格 | 用途 |
|---|---|---|
| 树莓派 4B | 4GB 内存及以上 | 运行 py-xiaozhi + 大脑 |
| Python | 3.10 - 3.12（py-xiaozhi 要求，不能用 3.13） | 运行环境 |
| USB 麦克风 | 16kHz 以上 | 小智收音 |
| USB 音箱 / USB 声卡 | — | 小智播放回复 |
| 按键开关 | 自锁/轻触均可 | 触发对话 |
| 杜邦线 + 电阻 | — | 按钮接 GPIO |
| 网络 | 能访问小智官方服务器 | 对话必须联网 |

---

## 6. 搭建步骤

### 6.1 准备 Python 3.10-3.12
树莓派默认 Python 3.11 满足要求，可直接用：
```bash
python3 --version   # 确认 ≥3.10 ≤3.12
```

### 6.2 克隆 py-xiaozhi
```bash
git clone https://github.com/huangjunsen0406/py-xiaozhi.git
cd py-xiaozhi
```

### 6.3 安装依赖（推荐 uv）
```bash
pip install uv
uv sync            # 或：pip install -e .
```

### 6.4 配置官方服务器
py-xiaozhi **默认自动从官方 OTA 获取服务器配置**，无需手动填写 WebSocket 地址：

- 官方 WebSocket 服务器：`wss://api.tenclass.net/xiaozhi/v1/`
- 设备授权地址：`https://xiaozhi.me/`
- `WEBSOCKET_URL` 与访问令牌由 OTA 自动下发，启动后自动更新

**首次启动会要求激活设备**：CLI 会显示一个验证码 → 打开浏览器访问 xiaozhi.me 输入验证码 → 绑定设备 → 之后自动连接对话。

### 6.5 配置 GPIO 按钮
用 GPIO 模式启动（仅树莓派/Linux，基于 `gpiozero`）：

```bash
python main.py --mode gpio
```

**默认引脚映射（BCM 编号，改 `src/ui/gpio/input.py` 的 `DEFAULT_PINS` 可自定义）**：

| 按键 | GPIO | 功能 |
|---|---|---|
| KEY1 | **GPIO 17** | **开始 / 停止对话**（小孩按这个和小智聊天） |
| KEY2 | GPIO 27 | 中断当前语音 |
| KEY3 | GPIO 22 | 切换自动/手动模式 |
| KEY4 | GPIO 23 | 退出程序 |

接线：按键一端接 GPIO，另一端接 GND（内部上拉，按下输出低电平）。
开发机（Windows）无法测 GPIO 模式（仅 Linux），先测 CLI 模式。

### 6.6 验证
- 无按钮测试：`python main.py --mode cli`，按回车/按键触发对话
- GPIO 测试：接好按钮，按下开始说话，再按结束

---

## 7. 与现有系统的关系

| 现有系统 | 小智集成 | 关系 |
|---|---|---|
| 大脑（决策/音效/协议） | py-xiaozhi 独立进程 | **并列运行**，互不阻塞 |
| 引擎轰鸣/鸣笛 | USB 音箱（音效） | 不同声卡，物理隔离 |
| 对讲机（家长） | py-xiaozhi 对话 | 都走音频，但设备/通道分离 |
| 语音控制（vosk 指令） | py-xiaozhi（自由对话） | vosk 是"指令"，小智是"对话"，可共存 |

---

## 8. 验证计划

1. **连通性**：CLI 模式跑通"文字/按键触发 → 小智回复"（先不接按钮）
2. **语音链路**：USB 麦克风说话 → 小智理解并语音回复
3. **按钮触发**：GPIO 按钮按下开始/结束对话
4. **音频隔离**：引擎声播放时，小智对话仍清晰（不同声卡）

---

## 9. 当前搭建状态（2026-08-07）

已在开发机完成：
- ✅ clone `py-xiaozhi` 到 `software/raspberry_pi/py-xiaozhi/`（第三方项目，不入库）
- ✅ `uv sync --python 3.11` 装好核心依赖（numpy/sounddevice/websockets/opuslib/sherpa-onnx 等）
- ✅ **Opus 库自动加载成功**（Windows 用内置 `libs/libopus/win/x64/opus.dll`；树莓派用内置 `libs/libopus/linux/arm64/libopus.so`，都无需手动装）
- ✅ 官方服务器默认配置（OTA 自动获取 `wss://api.tenclass.net/xiaozhi/v1/`）

### 首次运行与设备激活（需要在真实终端操作）

**Windows 开发机验证**（PowerShell）：
```powershell
cd software/raspberry_pi/py-xiaozhi
.venv\Scripts\python.exe main.py --mode cli
```
- 首次会显示**激活码** → 打开浏览器访问 `https://xiaozhi.me/` 输入验证码 → 绑定设备
- 激活后按提示按键/回车开始对话（用电脑麦克风说话、音箱听回复）

**树莓派部署**（`--mode gpio`，仅 Linux）：
```bash
cd ~/py-xiaozhi
python main.py --mode gpio      # GPIO17 按键：按下开始对话，再按结束
```
- 接好 GPIO17 按钮、USB 麦克风、USB 音箱
- 激活流程同上（激活一次后记住设备）

> 备注：开发机（Windows）无法测 GPIO 模式（仅 Linux），激活和对话用 CLI 模式验证即可。

---

## 10. 风险与注意

- **Python 版本**：py-xiaozhi 要求 3.10-3.12，现有 venv 是 3.13，需独立环境
- **官方服务器可用性**：以 py-xiaozhi 文档/配置里的服务器地址为准，若官方服务不可用需自建
- **树莓派性能**：4GB 内存够跑 py-xiaozhi，但若同时跑大脑+音效，建议 4GB+ 或 8GB
- **首次运行**：需 `uv sync` 安装依赖，且每次更新 main 分支需重装依赖
