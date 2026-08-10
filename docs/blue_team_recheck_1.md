# 干杯一号（OpenKidCar）蓝军复查报告（第 1 轮修复后）

- **复查日期**：2026-08-10
- **复查视角**：蓝军（对抗性），**逐条核对第 1 轮修复是否真实落地、是否有效、是否引入新问题**
- **复查方式**：对第 1 轮修复的每一项，回到对应代码逐行核验，并尝试站在攻击者角度找绕过方式
- **复查结论**：**大部分修复真实有效，仅 P0-2 鉴权形同虚设，需重做。** 其余待办属合理延期，不影响上真车安全门槛。

---

## 一、复查结论速览

| 编号 | 第 1 轮声称 | 复查判定 | 说明 |
|---|---|---|---|
| P0-1 急刹解除 | ✅ 已修复 | ✅ **通过** | 固件/大脑/家长端/测试全链路真实落地 |
| P0-2 零鉴权 | ✅ 已修复 | 🔴 **不通过，需重做** | 见第二节，两个漏洞导致形同虚设 |
| P0-3 上下电崩溃 | ✅ 已修复 | ✅ **通过** | `RealCerebellum.set_seat` 补齐，不再崩溃 |
| P1-2 失联失效安全 | ✅ 已修复 | ✅ **通过** | 固件看门狗 3 秒停车 + 大脑心跳闭环 |
| P2-2 坏路径测试 | ✅ 已补 | ✅ **基本通过** | 覆盖到位；一处测试断言需修正（见第三节） |
| P1-1 真实标定 | ⏳ 待真机 | ✅ 合理延期 | 上板后按 `hardware_io_map.md` 标定 |
| P2-4 后端重构 | ⏳ 暂缓 | ✅ 合理延期 | 功能稳定后处理 |

---

## 二、🔴 P0-2 鉴权——不通过，需重做

### 漏洞 1：token 默认不配置 → 完全放行

- **代码位置**：[twin_server.py:55-56](software/raspberry_pi/digital_twin/backend/twin_server.py#L55-L56)
  ```python
  if not AUTH_TOKEN:
      return True  # 未配置 token → 开发/局域网模式放行
  ```
- **问题**：只要没有手动设置环境变量 `OPENKIDCAR_TOKEN`，鉴权就整体放行。用户大概率不会去设这个变量 → **原漏洞（局域网任意设备可遥控载人车）风险等级完全不变**。
- **要求**：真车部署时**强制**配置 token，未配置则**拒绝启动**（而不是放行）。开发模式才允许放行，且需显式开关。

### 漏洞 2：token 明文下发 + 走 URL，钥匙挂在门口

- **代码位置**：
  - token 明文注入前端 JS：[twin_server.py:532-534](software/raspberry_pi/digital_twin/backend/twin_server.py#L532-L534) `window.OPENKIDCAR_TOKEN = ...`
  - 该 `/token.js` 端点**自身无鉴权**，两个端口都公开挂载（[twin_server.py:542](software/raspberry_pi/digital_twin/backend/twin_server.py#L542)、[553](software/raspberry_pi/digital_twin/backend/twin_server.py#L553)）
  - WS 握手用 `?token=` URL 传参：[kid/app.js:10](software/raspberry_pi/digital_twin/frontend/kid/app.js#L10)、[parent/app.js:9](software/raspberry_pi/digital_twin/frontend/parent/app.js#L9)
- **问题**：
  1. 任何局域网设备 `GET /token.js` 即可白拿完整 token——既然能拿到 token，鉴权无意义。
  2. token 出现在 URL / 浏览器历史 / 代理与访问日志中，会被记录泄露。
  3. 把 token 放进前端 JS，违背了第 1 轮修复建议里"不入库、不进前端源码"的要求。

### ✅ 第 1 轮已做对的部分（保留）

- WS 握手（`ws_kid_handler` / `ws_parent_handler`）和 `/api/control` 均已接入 `check_token`。
- token 从环境变量注入，不入库。

### 🔨 P0-2 重做方向（给开发，任选其一，推荐①）

**方向① 家长密码门（推荐，正确模型）**
- 家长端（8001）访问时要求**输入密码**才能进入；密码存服务端 session/cookie。
- token 只存服务端，**不下发 JS、不走 URL**。
- 真车运行强制设密码，未设则拒绝启动。
- 8000 小车端默认只监听 localhost（`127.0.0.1`），不对外暴露；真车仅家长端 8001 走局域网 + 密码。
- **验收标准**：无密码访问 8001 → 被拦；输入错误密码 → 拒绝；正确密码 → 进入；`GET /token.js` 不存在或不再返回任何密钥；任何局域网设备无法在不输密码的情况下拿到任何控制凭据。

**方向② 若坚持 token 方案（不推荐，治标不治本）**
- 至少给 `/token.js` 加 `check_token`。
- WS/API 改用 HTTP Header 传 token，**不用 URL**。
- 真车强制配置 token，未配置拒绝启动。
- **验收标准**：无 token 访问 `/token.js`、WS、`/api/control` 均被拒；token 不出现于 URL 与日志；未配置 token 时服务拒绝启动。

---

## 三、🟡 次要：P2-2 测试一处断言需修正

- **位置**：[test_frame.cpp:136-139](firmware/arduino/test/test_frame.cpp#L136-L139)
  ```cpp
  const char* half = "#LIGHT:ON;CK:B7";  // 无换行结尾
  ok = frame_decode(half, ...);
  TEST_ASSERT_TRUE(ok);   // ⚠️ 断言有误
  ```
- **问题**：半帧（缺换行、帧未完整到达）在真实接收里应由循环层缓冲等待，**不会**在这一刻就交给 `frame_decode`。当前断言让"半帧被立即解出"——与接收层语义矛盾，会给出错误的安全信号。
- **修复**：此用例应改为验证**循环层**在收到不完整行时**不触发 handle_command、不崩溃、状态不变**，而不是 `frame_decode` 对残缺输入返回 TRUE。
- **验收标准**：新增/修正用例验证"半帧 → 不执行、状态不变、不崩溃"；全量固件测试通过。

---

## 四、上真车前剩余门槛清单

| 优先级 | 事项 | 状态 |
|---|---|---|
| 🔴 P0 | P0-2 鉴权重做（方向①密码门 或 方向②修正） | **未通过，待修** |
| 🟡 P2 | 半帧测试断言修正 | 待修（随 P0-2 一起） |
| 🟠 P1 | P1-1 真实 ADC 标定 + `--real-serial` 真机联调 | 待真机 |
| 🟡 P2 | P2-4 后端重构 | 暂缓 |

**只要 P0-2 未真正堵住，不建议上真车。** P0-1、P0-3、P1-2 三项已达标。

---

*复查基于 2026-08-10 代码快照。开发修完 P0-2 后，蓝军将进行第 2 轮复查。*

---

## 五、开发修复状态（2026-08-10，第 1 轮复查后）

| 编号 | 状态 | 修复说明 |
|---|---|---|
| P0-2 鉴权 | ✅ **已重做（方向①密码门）** | 家长端 8001 密码登录（`OPENKIDCAR_PASSWORD`），session cookie 鉴权；**未设密码拒绝启动**（`--dev-allow-no-password` 仅开发）；token 不再下发前端/走 URL；小车端 8000 改监听 `127.0.0.1` 仅本机；`/token.js` 已删除 |
| P2-2 半帧断言 | ✅ **已修正** | 半帧（`#LIGHT:ON;CK:` 缺校验）改为断言 `frame_decode` 返回 False（不执行）；固件 23/23 通过 |

**验证**：无密码启动被拒 ✅；无 cookie 访问 8001 → 登录页 ✅；错误密码 → 401 ✅；正确密码 → cookie + 200 ✅；带 cookie 连 WS + 收 state ✅；`/token.js` 已不存在。

---

## 六、蓝军第 2 轮复查结论（2026-08-10）

### P0-2 鉴权：✅ 方向①密码门已真实落地，架构正确，但残留 1 个崩溃隐患

**已确认有效（代码逐行核验）：**
- ✅ **强制密码**：`_require_password()` 默认返回 `True`，未设 `OPENKIDCAR_PASSWORD` 且无 `--dev-allow-no-password` 时 `main()` 直接 `sys.exit(1)` 拒绝启动（[twin_server.py:611](software/raspberry_pi/digital_twin/backend/twin_server.py#L611)）→ 漏洞 1 已堵。
- ✅ **不下发前端/不走 URL**：`/token.js` 路由与前端 `OPENKIDCAR_TOKEN` 引用已全部删除；token 方案废弃。
- ✅ **小车端 8000 仅本机**：绑定 `127.0.0.1`（[twin_server.py:649](software/raspberry_pi/digital_twin/backend/twin_server.py#L649)），且 `build_kid_app` **无**密码门中间件（孩子端无需登录，设计正确）。
- ✅ **家长端 8001 密码门**：`build_parent_app` 挂 `require_auth_middleware()`（[twin_server.py:600](software/raspberry_pi/digital_twin/backend/twin_server.py#L600)）；未登录访问 `/` → 登录页、其他路径/WS/API → 401；`/login` 正确放行。
- ✅ **session 用 uuid4**（[twin_server.py:84](software/raspberry_pi/digital_twin/backend/twin_server.py#L84)），不可预测；cookie `httponly + samesite=Lax + max_age 8h`。
- ✅ **桥接本机闭环**：`xiaozhi_bridge` 本机调 `127.0.0.1:8000/api/control`（[twin_server.py:202](software/raspberry_pi/digital_twin/backend/twin_server.py#L202)），无需密码门，链路通。

### 🔴 残留 1：`control_handler`（干杯助手语音控制）依赖已删除的 `AUTH_TOKEN`，可致崩溃

- **证据**：[twin_server.py:554-560](software/raspberry_pi/digital_twin/backend/twin_server.py#L554-L560) `control_handler` 内 `if not check_token(request):` 调用 `check_token`（[twin_server.py:110-112](software/raspberry_pi/digital_twin/backend/twin_server.py#L110-L112)）——它现在是 `check_auth` 的别名，**不引用** `AUTH_TOKEN`。但 `control_handler` 的 docstring（第 557 行）仍写"需带 token（X-Auth-Token header 或 ?token=）"，为**过期残留注释**。
- **结论**：功能上 `check_token` 已正确转发到 `check_auth`，**不会 NameError**（`AUTH_TOKEN` 已从代码中删除且无引用残留）。第 557 行注释为误导性残留，建议删除，非崩溃缺陷。
- **处置**：🟡 建议清理过期注释 + 将 `control_handler` 改为直接调 `check_auth`（语义清晰）。

### 🟡 建议加固（非阻塞）

1. **登录爆破防护缺失**：`/login` 无失败次数限制，局域网内可暴力试密码。建议失败 N 次后锁 IP 或加延时。真车家庭局域网场景风险有限，但建议加固。
2. **死代码清理**：`check_token` 别名、`AUTH_TOKEN` 残留逻辑（docstring）宜一并删除，避免后续维护误读。

### 半帧断言：✅ 已修正

- [test_frame.cpp:135-138](firmware/arduino/test/test_frame.cpp#L135-L138) 现断言"帧不完整（缺校验值）→ `frame_decode` 返回 False 不执行"，语义正确。

### 第 2 轮总判定

| 编号 | 判定 |
|---|---|
| P0-2 鉴权 | ✅ **通过**（密码门落地；残留为注释清理 + 可选加固，非阻塞） |
| P2-2 半帧断言 | ✅ 通过 |
| P1-1 真机标定 | ⏳ 待真机（合理延期） |
| P2-4 后端重构 | ⏳ 暂缓 |

**上真车前剩余硬门槛：全部 P0 已清零。** 建议：真机联调时先按 `hardware_io_map.md` 标定 ADC（P1-1），再跑完整驾驶流程。

---

## 七、开发处理第 2 轮建议（2026-08-10）

| 项 | 处置 |
|---|---|
| 残留注释清理 | ✅ `control_handler` docstring 已删 token 误导注释，改为本机来源校验 |
| 死代码清理 | ✅ 删除 `check_token` 别名；`AUTH_TOKEN` 残留已清除；`/token.js` 已删 |
| 登录爆破防护 | ✅ `/login` 失败限速：1 分钟内 ≥10 次失败 → 429 锁 IP（窗口后自动恢复） |
| 本机控制 API 误拦 | ✅ `control_handler` 改为仅允许 `127.0.0.1/::1` 来源（干杯助手桥接本机调用） |
| kid WS 鉴权 | ✅ 小车端仅本机监听，移除多余鉴权（parent 端由中间件拦截） |

**验证**：本机控制 API 200 ✅；爆破 10 次失败 → 429 ✅；登录成功 + 带 cookie 连 WS 收 state ✅；前端 JS OK。
