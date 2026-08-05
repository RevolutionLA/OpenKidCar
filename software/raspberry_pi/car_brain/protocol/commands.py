"""命令常量定义。

必须与 firmware/arduino/src/protocol/commands.h 保持一致
协议规格见 docs/communication_protocol.md
"""

# ---- 下行命令（大脑 -> 小脑）----
GEAR = "GEAR"       # 参数：1-4 速度档位
LIGHT = "LIGHT"     # 参数：ON / OFF 前大灯
STRIP = "STRIP"     # 参数：模式,颜色,亮度 RGB灯带
TURN = "TURN"       # 参数：L / R / OFF 转向灯
MUTE = "MUTE"       # 参数：ON / OFF 引擎音效静音
HORN = "HORN"       # 参数：ON / OFF 鸣笛
BRAKE = "BRAKE"     # 参数：ON / OFF 制动（缓刹）
EBRK = "EBRK"       # 参数：ON 远程急刹（最高优先级）
STATUS = "STATUS"   # 参数：GET 请求状态上报
PING = "PING"       # 心跳请求

# ---- 上行命令（小脑 -> 大脑）----
STAT = "STAT"       # 状态上报：速度,油门,档位,电压,温度,电流
BTN = "BTN"         # 按钮事件：按钮名,PRESS/RELEASE
SEAT = "SEAT"       # 就座 / 离座：ON / OFF
PONG = "PONG"       # 心跳响应
ACK = "ACK"         # 命令应答：OK / ERR:原因
READY = "READY"     # 上电就绪：协议版本

# ---- 按钮名（BTN 命令参数）----
LIGHT_BTN = "LIGHT_BTN"  # D24 大灯开关
MUTE_BTN = "MUTE_BTN"    # D23 静音开关
STRIP_BTN = "STRIP_BTN"  # D25 灯带开关
HORN_BTN = "HORN_BTN"    # D26 喇叭按钮
EBRK_BTN = "EBRK_BTN"    # D22 一键刹车
TALK_BTN = "TALK_BTN"    # D27 对讲按钮
