# 开发笔记与状态存档

> 本文档记录截至 **2026-08-07** 的项目关键信息，用于上下文压缩（compact）后快速恢复。
> 时间线详情见 [development_log.md](development_log.md) 与 `logs/开发日记/`。

---

## 1. 当前项目状态

| 模块 | 状态 | 位置 |
|---|---|---|
| 通信协议 V0.3 | ✅ 可用 | [communication_protocol.md](communication_protocol.md) |
| 小脑代码骨架（Arduino） | ✅ 可编译（Mega 固件 + native 测试 10/10） | `firmware/arduino/` |
| 大脑代码骨架（Python） | ✅ 可用（测试 15 项通过） | `software/raspberry_pi/` |
| 语音控制（vosk） | ✅ 可用（唤醒词"干杯出来"） | `software/raspberry_pi/car_brain/voice.py` |
| 数字孪生网页 v1（双端） | ✅ **已重设计**：弃 3D 车模，改"小车端仪表盘+控制区 / 家长端 GPS+电量+对讲+视频"，双端共享同一套大脑+小脑，双 WebSocket | `software/raspberry_pi/digital_twin/`（本地，gitignore） |
| GitHub | ✅ 已推送（**不含**数字孪生网页） | `https://github.com/RevolutionLA/OpenKidCar` |

**当前版本已推送**：`main` → `c1bfe4a`（含 Day 3 开发日志，无网页）。
本地备份分支：`backup-main`（含完整网页版）。

---

## 2. 核心架构（上位机 / 下位机）

```
大脑（上位机）树莓派                   小脑（下位机）Arduino
┌────────────────────┐              ┌────────────────────┐
│ AI / 决策 / 语音    │   UART 串口   │ 感知 / 执行 / 实时  │
│ Raspberry Pi 4B    │ ◄──协议V0.3──► │ Arduino Mega 2560  │
│ software/raspberry │              │ firmware/arduino    │
└────────────────────┘              └────────────────────┘
```

- **大脑**：负责决策、AI、语音识别（需算力，不需要毫秒级实时）
- **小脑**：负责感知（踏板/按钮/传感器）与执行（电机/灯光），无操作系统、时序确定
- **数字孪生**：前端浏览器 ↔ WebSocket ↔ Python 后端（真实 Brain + CerebellumSim 内存管道），与真实硬件同构

**分层关键（HAL）**：逻辑层只调 `hal_*` 接口（`hal.h`），桌面模拟（`hal_sim.cpp`）和真实引脚（`hal_mega.cpp`）是不同实现。同一份逻辑可移植。

---

## 3. 技术栈与环境

| 项 | 说明 |
|---|---|
| 开发机 | Windows 11，Python 3.14（系统）+ **Python 3.13 venv**（语音/音频用） |
| Python venv | `software/raspberry_pi/.venv`（装 vosk、sounddevice、numpy、edge-tts、pygame、aiohttp、pyserial） |
| PlatformIO | 路径 `~/.platformio/penv/Scripts/pio.exe`；VSCode 插件已装 |
| MinGW 编译器 | w64devkit（`C:\Users\HW\w64devkit\w64devkit\bin`）—— native 编译必需 |
| 语音识别 | vosk 中文模型：`~/vosk-model-small-cn-0.22` |
| 语音反馈 | edge-tts（默认"晓晓"），环境变量 `TTS_VOICE` 换音色 |
| 数字孪生后端 | aiohttp（HTTP 静态 + WebSocket `/ws`） |
| 数字孪生前端 | Three.js 0.128（本地 `vendor/`，GLTFLoader 本地） |

**常用命令**：
```bash
# 小脑 native 测试
cd firmware/arduino && ~/.platformio/penv/Scripts/pio.exe test -e native
# 编译 Mega 固件
~/.platformio/penv/Scripts/pio.exe run -e mega2560
# 大脑测试
cd software/raspberry_pi && .venv/Scripts/python.exe -m unittest discover -s tests -v
# 语音控制（连 native 小脑）
.venv/Scripts/python.exe -m car_brain.app --native <exe> --voice
```

---

## 4. 数字孪生失败教训（重要）

这些是 2026-08-06/07 反复踩坑得到的，**重新设计时务必遵守**：

1. **灯光/方向要"跟模型节点走"，不要猜坐标**
   反复猜 CarConcept 车头方向失败（手算 +Z 是错的）。正确做法：灯光 mesh 直接挂到模型的真实车灯节点（`BodyHeadlights`/`BodyTaillights`），方向自动正确。
   → 权威验证用 Three.js `Matrix4`（与浏览器一致）：CarConcept 车头在 **-Z**（BodyHeadlights z=-2.38），车尾 **+Z**（BodyTaillights z=+1.93）。

2. **轮子收集陷阱**：`WheelFrontL` 是 **Group 不是 Mesh**，`if (o.isMesh)` 会跳过 → 前轮永不转向。收集轮子不要只看 `isMesh`。

3. **服务器必须 `Cache-Control: no-store`**：否则浏览器缓存导致"改了没变化"的假象。

4. **物理模型要积分式**：速度不能是"油门瞬间映射"（刹车不参与）。改成积分式：油门加速逼近目标、刹车/急刹减速。

5. **视觉类问题无法靠纯推理调试**：看不到渲染结果时，盲改必失败。对策：方向/灯光可调（按钮）、日志输出关键信息（轮子数、灯光挂接）。

6. **AI 生成的 3D 模型质量差**：尝试的开源卡丁车模型（summerengine 等）是碎片化的（1523 个碎块）。可靠模型源：Khronos glTF-Sample-Assets（CarConcept）、three.js 官方 ferrari（已被用户弃用）。

7. **音频**：引擎声用真实 CC0 录音（Creazilla engine.mp3，Public Domain）；油门 0 应无声；鸣笛暂为合成（待找 CC0 喇叭声）。

---

## 5. 本轮对话中的关键问答（小白开发者问题存档）

1. **大脑/小脑类比科学吗？** → 科学，即上位机/下位机，真实汽车也这么分层。
2. **代码能直接移植到树莓派/Arduino 吗？** → 分层正确（HAL）即可原样移植，只换硬件层。
3. **桌面模拟器是"一比一"吗？** → 模拟逻辑，不模拟物理（噪声/惯性无法模拟）。
4. **先硬件还是先软件？** → 先定接口契约（引脚/协议），再并行。
5. **协议是什么？为什么校验？** → 两端通信规则；校验防"传错当真"。
6. **要全想清楚才定义协议吗？** → 不需要，功能清单 + 接口契约即可。
7. **pygame 能做游戏级 3D 吗？** → 不能，2D 库，改用 Web Three.js。
8. **数字孪生真跑大脑小脑吗？** → 是（后端就是真实 Brain + CerebellumSim），物理真实度需逐步精细。

---

## 6. 下一步计划

1. ✅ **数字孪生 v1 已重设计**（2026-08-07，见 [Day 4 日志](../logs/开发日记/20260807-day4.md)）：弃 3D 车模，改双端架构 —— 小车端(8000)仪表盘区+控制区、家长端(8001)GPS+电量+对讲+视频，**双端共享同一套真实大脑+小脑**。
2. 打磨数字孪生 v1：视觉细节、对讲/视频体验、家长端实测反馈。
3. 继续打磨物理模型（加速度曲线、坡度等）。
4. 鸣笛换真实 CC0 喇叭声。
5. 双端稳定满意后，考虑把数字孪生网页正式纳入 GitHub 归档。

---

## 7. 用户偏好（开发方式）

- **中文交流**
- 作为**小白开发者**，重视：每一步的为什么、可验证的成果、过程的记录（开发日志）
- 每次有价值的推进 → 记入开发日志（`logs/开发日记/`）
- 远程（出差）开发 → 优先"不依赖硬件的可跑通"成果
- 代码与文档**尽量开源、可复刻**
