# 小脑工程（Arduino Mega 2560）

干杯一号的小脑固件 —— 负责感知（踏板/按钮/传感器）与执行（电机/灯光）。

## 架构

```
src/main.cpp          小脑主程序（平台无关逻辑）
src/protocol/         协议模块（纯 C++，不依赖 Arduino API）
  ├─ commands.h        命令常量（与 Python 端 commands.py 保持一致）
  ├─ crc8.h/.cpp       CRC8 校验
  └─ frame.h/.cpp      帧封装 / 解析
src/hal/              硬件抽象层（HAL）
  ├─ hal.h             HAL 接口
  ├─ hal_sim.cpp       桌面模拟实现（native 环境）
  └─ hal_mega.cpp      真实引脚实现（mega2560 环境）
test/test_frame.cpp   协议单元测试（Unity）
```

**分层原则**：`main.cpp` 和 `protocol/` 只调用 `hal.h` 定义的接口，不直接碰硬件。这样同一份逻辑能在 PC 模拟和真实板子上运行。

## 常用命令

```bash
# 编译并运行协议单元测试（无板子也能跑）
pio test -e native

# 编译桌面模拟程序（native exe，stdin/stdout 当串口）
pio run -e native
# 编译产物在 .pio/build/native/program.exe

# 编译真实固件（烧录到 Arduino Mega 2560）
pio run -e mega2560

# 烧录固件
pio run -e mega2560 -t upload
```

> 提示：VSCode 安装了 PlatformIO 后，可直接在 IDE 里点击对勾（build）和箭头（upload）。命令行用 `~/.platformio/penv/Scripts/pio.exe`。

## 桌面模拟演示（无需板子）

编译 native 程序后，它会把 **stdin 当串口接收、stdout 当串口发送**：

```bash
# 直接运行，观察按钮事件/状态上报（stderr 显示执行器动作）
.pio/build/native/program.exe
```

更完整的演示：用 Python 大脑端驱动它（见 [software/raspberry_pi](../../software/raspberry_pi/README.md)）：

```bash
cd ../../software/raspberry_pi
python -m car_brain.app --native ../firmware/arduino/.pio/build/native/program.exe --demo
```

## 真机接线

引脚分配见 [docs/hardware_io_map.md](../../docs/hardware_io_map.md)。
`hal_mega.cpp` 中已按该文档映射引脚。
