# 🛠️ 开发辅助工具

数字孪生前端开发时，"AI 看不见浏览器画面"是最大的痛点。
下面两个工具组合起来，让 AI 可以"间接看图"—— 验证 UI 文字、实时数据、布局与配色。

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

## 组合使用（验证流程）

1. `cdp_shot.py` 拿到真实渲染的截图（WS 已连、数据已更新）
2. `ocr.ps1` 读出截图文字，确认数据落地
3. 需要检查布局/配色时，用 pygame 做像素抽样或 ASCII 亮度图

> 依赖：`ocr.ps1` 需 Windows 10/11；`cdp_shot.py` 需本仓库 venv（aiohttp）。
