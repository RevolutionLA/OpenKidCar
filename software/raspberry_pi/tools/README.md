# 🛠️ 开发辅助工具

数字孪生前端开发时，"AI 看不见浏览器画面"是最大的痛点。
下面几个工具组合起来，让 AI 可以"看图"—— 验证 UI 文字、实时数据、布局与配色。

- **第 3 个工具是"真正能看懂画面"的视觉模型**，强烈推荐优先使用（见下）。

## 1. `ocr.ps1` —— Windows 自带 OCR 读图（零依赖）

用 Windows 系统自带的 OCR 引擎（支持中文，离线）识别图片中的文字。

```powershell
powershell -ExecutionPolicy Bypass -File tools/ocr.ps1 -ImagePath 截图.png          # 只输出文字
powershell -ExecutionPolicy Bypass -File tools/ocr.ps1 -ImagePath 截图.png -Boxes    # 带坐标框 [x,y x2,y2] 文字
```

- 中文小字识别率不高时，先用 pygame 把图片放大 1.5~2 倍再识别。
- 适合：确认页面渲染了什么文字、实时数据（电量/GPS/速度）有没有更新。

## 2. `cdp_shot.py` —— 真实等待的浏览器截图

headless Chrome 的 `--virtual-time-budget` 会"冻结真实时间"，导致 WebSocket 消息送不到页面，
截出来的图是"没连上"的空壳。用 Chrome DevTools Protocol 真实等待几秒再截图，拿到有实时数据的画面。

```bash
# 1. 先启动带调试端口的 Chrome（headless 也行）
chrome --headless=new --disable-gpu --remote-debugging-port=9222 --user-data-dir=/tmp/cdp about:blank

# 2. 截图（url, 输出路径, 等待秒数）
.venv/Scripts/python.exe tools/cdp_shot.py "http://localhost:8001/" shot.png 7
```

## 3. GLM 视觉模型 MCP —— AI 真正"看懂"画面（全局能力）

纯文本主模型（如 deepseek）看不了图。已配置智谱免费视觉模型把图片变成文字描述，
注入 Claude 的上下文 —— Claude Code 就"看见"了。

**这是全局能力，所有项目通用**（已注册到用户级 `~/.claude.json`，不是本仓库专属）：

- **server 位置**：`~/.claude/glm-vision/glm-vision-mcp.mjs`（零依赖 Node）
- **API Key**：`~/.claude/glm-vision/.env`（`ZHIPU_API_KEY=...`，不在任何 git 仓库内）
- **模型策略**：`glm-4.6v-flash` 优先，429 限流自动降级 `glm-4.1v-thinking-flash` → `glm-4v-flash`
- **工具名**：`describe_image`，接收图片路径，支持 png/jpg/jpeg/gif/webp/bmp（≤10MB）
- **生效条件**：重启 Claude Code 会话后，`describe_image` 自动出现在 Claude 工具列表

**手动验证（不依赖 Claude Code，任何目录可跑）**：

```bash
node ~/.claude/glm-vision/test_glm_vision_mcp.mjs "media/images/twin_parent_live.png" "用中文描述这张截图"
# 模拟完整 MCP 握手 → 调 GLM 看图 → 打印描述
```

**需要先给主模型"指路"**：新会话中如果 Claude 没主动发现图片，可以说
"用 glm-vision 的 describe_image 看一下 xxx.png"。

## 组合使用（验证流程）

1. `cdp_shot.py` 拿到真实渲染的截图（WS 已连、数据已更新）
2. **`describe_image`（GLM 视觉模型）直接看懂画面 —— 布局、配色、数据、图标一起描述**（首选）
3. `ocr.ps1` 精准提取小字文字时用（如坐标、数值）
4. 需要精确像素布局时，用 pygame 做像素抽样或 ASCII 亮度图

> 依赖：`ocr.ps1` 需 Windows 10/11；`cdp_shot.py` 需本仓库 venv（aiohttp）；GLM 视觉 MCP 需 Node ≥18 和有效 GLM API Key（全局配置于 `~/.claude/glm-vision/`）。

## 4. `cdp_check.py` —— DOM 级布局检查（一屏/元素位置）

精确验证"是否一屏不滚动"、面板位置、速度环状态：

```bash
# url, 等待秒, 宽, 高, mobile
.venv/Scripts/python.exe tools/cdp_check.py "http://localhost:8000/" 6 1280 800 0
# 输出 oneScreen(true/false)、scrollH、各面板 bounding rect
```

## 5. `test_ws_link.py` —— 双端 WS 链路端到端测试

不依赖浏览器/摄像头，模拟小车端 + 家长端两个 WebSocket，验证：

- 双端收到同一辆车的状态（数据一致）
- 家长端 call → 小车端收到
- 小车端 video/audio → 家长端收到
- 家长端远程急刹 → 小车端 ebrk 状态变化
- 小车端档位命令 → 家长端状态同步

```bash
.venv/Scripts/python.exe tools/test_ws_link.py
# 6 项全部 ✅ 即通信链路正常
```
