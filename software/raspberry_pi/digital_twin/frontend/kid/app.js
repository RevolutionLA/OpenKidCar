/* 干杯一号 · 小车端
   真实信号链路：浏览器操作 → WS /ws → 大脑决策 → 协议 V0.3 → 小脑执行 → 状态快照返回
   对讲 / 视频帧通过 WS 与家长端互转。
   音效：Web Audio 实时合成引擎轰鸣 + 喇叭。
*/
"use strict";

const $ = (id) => document.getElementById(id);
const wsUrl = (location.protocol === "https:" ? "wss" : "ws") + "://" + location.host + "/ws";
const log = $("log");

function addLog(text) {
  const t = new Date().toLocaleTimeString("zh-CN", { hour12: false });
  const div = document.createElement("div");
  div.className = "line";
  div.innerHTML = `<time>${t}</time><span class="tag">·</span>${text}`;
  log.prepend(div);
  while (log.children.length > 80) log.lastChild.remove();
}

// ================= WebSocket =================
const ws = new WebSocket(wsUrl);

ws.onopen = () => { addLog("✅ 已连接小脑（大脑在线）"); };
ws.onclose = () => { addLog("⚠️ 连接断开，正在重连…"); setTimeout(() => location.reload(), 2000); };
ws.onerror = () => addLog("❌ WebSocket 错误");

ws.onmessage = (e) => {
  let m;
  try { m = JSON.parse(e.data); } catch { return; }
  if (m.type === "state") render(m.data);
  else if (m.type === "log") addLog(m.text);
  else if (m.type === "audio") playAudio(m.data);
  else if (m.type === "xiaozhi_reply") accumulateXiaozhiReply(m.data);
  else if (m.type === "xiaozhi_tts_end") flushXiaozhiReply();
  else if (m.type === "xiaozhi_log") addLog(m.text);
  // 单向视频：小车只推送自己的视频给家长，不接收家长端视频流
  else if (m.type === "call") startVideoCall(true);
  else if (m.type === "hangup") stopVideoCall();
};

function send(obj) {
  if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(obj));
}

// ================= 速度环（270° 弧 + 指针同步） =================
const RING_ARC = 433.5;   // 270/360 × 2π×92
const RING_CIRC = 578.0;  // 整圆 2π×92
const needle = $("needle");
const ticks = $("ticks");

(function buildTicks() {
  for (let v = 0; v <= 100; v += 10) {
    const big = v % 20 === 0;
    const a = (v / 100) * 270 - 135;
    const rad = (a * Math.PI) / 180;
    const r1 = big ? 78 : 83;
    const r2 = 92;
    const x1 = 110 + r1 * Math.cos(rad), y1 = 110 + r1 * Math.sin(rad);
    const x2 = 110 + r2 * Math.cos(rad), y2 = 110 + r2 * Math.sin(rad);
    const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
    line.setAttribute("class", "tick" + (big ? " big" : ""));
    line.setAttribute("x1", x1); line.setAttribute("y1", y1);
    line.setAttribute("x2", x2); line.setAttribute("y2", y2);
    ticks.appendChild(line);
  }
})();

function updateSpeed(kmh, max) {
  const pct = Math.min(100, (kmh / max) * 100) / 100;
  $("speed").textContent = Math.round(kmh);
  const ring = document.querySelector(".ring-val");
  const dash = RING_ARC * pct;                       // 弧长 0..433.5
  ring.style.strokeDasharray = `${dash.toFixed(1)} ${(RING_CIRC - dash).toFixed(1)}`;
  const angle = pct * 270 - 135;                     // 指针 -135°..+135°
  needle.style.transform = `rotate(${angle}deg)`;
}

// ================= 音效（真实引擎录音 + Web Audio） =================
let ac = null, eng = null, engineAudio = null;

function initAudio() {
  if (ac) {
    // 浏览器自动播放策略：AudioContext 默认 suspended，需在用户手势后恢复
    if (ac.state === "suspended") ac.resume().catch(() => {});
    return;
  }
  try {
    ac = new (window.AudioContext || window.webkitAudioContext)();
    ac.resume().catch(() => {});

    // 真实引擎录音（CC0 engine.mp3，油门越大转速越高）
    engineAudio = new Audio("/static/assets/engine.mp3");
    engineAudio.loop = true;
    engineAudio.preload = "auto";
    engineAudio.volume = 0;
    window.engineAudio = engineAudio;   // 暴露便于调试
    eng = { ready: false };
    engineAudio.addEventListener("canplaythrough", () => { eng.ready = true; });
    engineAudio.addEventListener("error", () => { addLog("⚠️ 引擎录音加载失败，用合成声"); });
  } catch (e) {
    ac = null; eng = null;
    addLog("❌ 音效初始化失败: " + e.message);
  }
}

function updateEngine(throttle, speed, muted, online, ebrk, brake) {
  if (!ac) return;
  // 急刹 / 深刹车 → 引擎声停止（真实车辆急刹松油门）
  const stopping = ebrk || brake > 10;
  // 油门 0 或急刹 → 完全无声；油门越大声音越大
  const vol = (stopping || throttle <= 0) ? 0 : (throttle / 100) * 0.4;
  // 速度越大音调越高（真实录音变速）
  const rate = stopping ? 0.5 : 0.6 + (throttle / 100) * 0.3 + (speed / 25) * 0.6;
  const target = (muted || !online) ? 0 : vol;
  if (engineAudio) {
    engineAudio.volume = target;
    engineAudio.playbackRate = rate;
    if (target > 0.01 && engineAudio.paused) engineAudio.play().catch(() => {});
    else if (target <= 0.01 && !engineAudio.paused) engineAudio.pause();
  }
}

function honk() {
  if (!ac) initAudio();
  if (!ac) return;
  // 真实 CC0 喇叭声（BigSoundBank Car honking）
  const h = new Audio("/static/assets/horn.mp3");
  h.volume = 0.7;
  h.play().catch(() => {});
}

// ================= 状态渲染 =================
const lamps = {
  light: $("lamp-light"), strip: $("lamp-strip"),
  turnl: $("lamp-turnl"), turnr: $("lamp-turnr"),
  brake: $("lamp-brake"), ebrk: $("lamp-ebrk"), mute: $("lamp-mute"),
};

function render(s) {
  const max = { 1: 10, 2: 15, 3: 20, 4: 25 }[s.gear] || 15;
  updateSpeed(s.speed, max);
  updateEngine(s.throttle, s.speed, s.mute, s.online, s.ebrk, s.brake);

  $("g-throttle").style.width = s.throttle + "%";
  $("g-throttle-v").textContent = s.throttle;
  $("g-brake").style.width = s.brake + "%";
  $("g-brake-v").textContent = s.brake;
  $("g-motor").style.width = s.motor + "%";
  $("g-motor-v").textContent = s.motor;

  $("d-bat").textContent = Math.round(s.battery_pct) + "%";
  $("d-volt").textContent = s.voltage.toFixed(1) + " V";
  $("d-cur").textContent = s.current.toFixed(1) + " A";
  $("d-temp").textContent = s.temp.toFixed(0) + " ℃";
  $("d-gps").textContent = s.gps.lat.toFixed(6) + " , " + s.gps.lng.toFixed(6);

  setLamp(lamps.light, s.light);
  setLamp(lamps.strip, s.strip);
  setLamp(lamps.turnl, s.turn === "L");
  setLamp(lamps.turnr, s.turn === "R");
  setLamp(lamps.brake, s.brake_light > 0 || s.brake > 10);
  setLamp(lamps.ebrk, s.ebrk);
  setLamp(lamps.mute, s.mute);

  document.querySelectorAll(".gear").forEach((b) =>
    b.classList.toggle("active", parseInt(b.dataset.g) === s.gear));
  $("hud-gear").textContent = s.gear;
  $("speed-gear").textContent = "D" + s.gear;

  $("chip-brain").classList.toggle("on", s.online);
  $("chip-cere").classList.toggle("on", s.online);
  $("btn-ebrk").classList.toggle("on", s.ebrk);

  syncSwitch($("sw-light"), s.light);
  syncSwitch($("sw-mute"), s.mute);
  syncSwitch($("sw-strip"), s.strip);
  syncSlider($("throttle"), s.throttle, $("throttle-val"));
  syncSlider($("brake"), s.brake, $("brake-val"));
  syncSlider($("steer"), Math.round(s.steer * 100), $("steer-val"), "°");
}

function setLamp(el, on) { el.classList.toggle("on", !!on); }
function syncSwitch(btn, on) { if (btn.dataset.own !== "1") btn.classList.toggle("on", !!on); }
function syncSlider(slider, v, readEl, suffix = "") {
  if (slider.dataset.own !== "1") {
    slider.value = v;
    if (readEl) readEl.textContent = v + suffix;
  }
}

// ================= 档位 =================
document.querySelectorAll(".gear").forEach((b) => {
  b.addEventListener("click", () => {
    send({ type: "gear", value: parseInt(b.dataset.g) });
    addLog(`档位 → D${b.dataset.g}`);
  });
});

// ================= 转向手柄 =================
const steer = $("steer");
steer.addEventListener("input", () => {
  steer.dataset.own = "1";
  const v = parseInt(steer.value);
  $("steer-val").textContent = Math.round(v) + "°";
  send({ type: "steer", value: v / 100 });
});
steer.addEventListener("change", () => delete steer.dataset.own);

// ================= 油门 / 刹车 =================
bindSlider($("throttle"), "throttle", $("throttle-val"));
bindSlider($("brake"), "brake", $("brake-val"));

function bindSlider(slider, type, readEl) {
  slider.addEventListener("input", () => {
    initAudio(); // 用户手势：激活音频
    slider.dataset.own = "1";
    const v = parseInt(slider.value);
    if (readEl) readEl.textContent = v;
    send({ type, value: v });
  });
  slider.addEventListener("change", () => delete slider.dataset.own);
}

// ================= 开关 =================
bindToggle($("sw-light"), "light", "大灯");
bindToggle($("sw-mute"), "mute", "静音");
bindToggle($("sw-strip"), "strip", "灯带");

function bindToggle(btn, type, label) {
  btn.addEventListener("click", () => {
    initAudio();
    const on = !btn.classList.contains("on");
    btn.dataset.own = "1";
    btn.classList.toggle("on", on);
    send({ type, value: on });
    addLog(`${label} ${on ? "开" : "关"}`);
    setTimeout(() => delete btn.dataset.own, 400);
  });
}

// 喇叭（按住响 + 音效）
$("sw-horn").addEventListener("pointerdown", () => { initAudio(); honk(); send({ type: "horn", value: true }); });
$("sw-horn").addEventListener("pointerup", () => send({ type: "horn", value: false }));
$("sw-horn").addEventListener("pointerleave", () => send({ type: "horn", value: false }));

// ================= 急刹（toggle） =================
$("btn-ebrk").addEventListener("click", () => {
  initAudio();
  send({ type: "btn", name: "EBRK_BTN" });
  addLog("急刹按钮按下（再次按下解除）");
});

// ================= 语音控制 =================
$("sw-voice").addEventListener("click", () => {
  initAudio();
  send({ type: "voice" });
  addLog("🎙 语音控制切换");
});

// ================= 对讲（PTT 按住说话 → 家长） =================
const talkPlayer = $("talk-player");
let recorder = null, recChunks = [];

async function ensureMic() {
  if (recorder) return true;
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    recorder = new MediaRecorder(stream);
    recChunks = [];
    recorder.ondataavailable = (e) => { if (e.data.size) recChunks.push(e.data); };
    recorder.onstop = () => {
      const blob = new Blob(recChunks, { type: recorder.mimeType || "audio/webm" });
      const reader = new FileReader();
      reader.onload = () => send({ type: "audio", from: "kid", data: reader.result });
      reader.readAsDataURL(blob);
      recChunks = [];
    };
    return true;
  } catch (err) {
    addLog("❌ 无法使用麦克风: " + err.message);
    return false;
  }
}

const ptt = $("ptt");
let pttOn = false;
ptt.addEventListener("pointerdown", async (e) => {
  e.preventDefault();
  if (!(await ensureMic())) return;
  pttOn = true;
  ptt.classList.add("talking");
  recChunks = [];
  recorder.start();
});
ptt.addEventListener("pointerup", () => {
  if (!pttOn) return;
  pttOn = false;
  ptt.classList.remove("talking");
  if (recorder.state !== "inactive") recorder.stop();
});
ptt.addEventListener("pointerleave", () => ptt.dispatchEvent(new Event("pointerup")));

function playAudio(dataUrl) {
  talkPlayer.src = dataUrl;
  talkPlayer.play().catch(() => {});
}

// ================= 视频（单向：小车只推送给家长，不接收） =================
let localStream = null, sendTimer = null, pushing = false;
const sendCanvas = $("send-canvas");
const sendCtx = sendCanvas.getContext("2d");

async function startVideoCall(auto = false) {
  if (pushing) return; // 已在推流
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    addLog("❌ 当前浏览器/环境不支持摄像头（需要 localhost 或 HTTPS）");
    return;
  }
  try {
    addLog("📷 正在打开摄像头，画面推送给家长…");
    localStream = await navigator.mediaDevices.getUserMedia({
      video: { width: 320, height: 240 }, audio: false,
    });
  } catch (err) {
    addLog("❌ 无法使用摄像头: " + err.message + "（请允许摄像头权限，需 localhost 或 HTTPS）");
    return;
  }
  pushing = true;
  $("local-video").srcObject = localStream;
  sendTimer = setInterval(() => {
    if (!localStream) return;
    sendCtx.drawImage($("local-video"), 0, 0, 320, 240);
    send({ type: "video", from: "kid", data: sendCanvas.toDataURL("image/jpeg", 0.35) });
  }, 200);
  addLog(auto ? "📷 视频已推送给家长" : "📷 视频推流中");
}

function stopVideoCall() {
  if (!pushing) return; // 已停止，避免 hangup 循环转发
  pushing = false;
  if (sendTimer) { clearInterval(sendTimer); sendTimer = null; }
  if (localStream) { localStream.getTracks().forEach((t) => t.stop()); localStream = null; }
  $("local-video").srcObject = null;
  send({ type: "hangup" });
  addLog("📷 视频推送已停止");
}

$("btn-video").addEventListener("click", () => {
  initAudio();
  if (localStream) { stopVideoCall(); return; }
  send({ type: "call" });           // 通知家长端：我要开始推流了
  startVideoCall(true);             // 开摄像头推流
});

// ================= 干杯助手对话（按住说话） =================
const xzBtn = $("btn-xiaozhi");
let xzStream = null, xzAudioCtx = null, xzProcessor = null;
let xzTalking = false;

async function xzStartMic() {
  if (xzStream) return true;
  try {
    xzStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    return true;
  } catch (err) {
    addLog("❌ 干杯助手麦克风不可用: " + err.message);
    return false;
  }
}

function xzStart() {
  xzStartMic().then(ok => {
    if (!ok) return;
    xzTalking = true;
    xzBtn.classList.add("talking");
    xzBtn.textContent = "🎙 说话中…";
    // 用 AudioContext 采集 16kHz 单声道 PCM（协议要求）
    xzAudioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
    const src = xzAudioCtx.createMediaStreamSource(xzStream);
    xzProcessor = xzAudioCtx.createScriptProcessor(4096, 1, 1);
    src.connect(xzProcessor);
    xzProcessor.connect(xzAudioCtx.destination);
    send({ type: "xiaozhi", action: "start" });
    xzProcessor.onaudioprocess = (e) => {
      if (!xzTalking) return;
      const buf = e.inputBuffer.getChannelData(0);
      const pcm = new Int16Array(buf.length);
      for (let i = 0; i < buf.length; i++) {
        pcm[i] = Math.max(-1, Math.min(1, buf[i])) * 32767;
      }
      const bytes = new Uint8Array(pcm.buffer);
      let bin = "";
      for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
      send({ type: "xiaozhi", action: "audio", data: btoa(bin) });
    };
    addLog("🎙 干杯助手对话中，请按着说…");
  });
}

function xzStop() {
  if (!xzTalking) return;
  xzTalking = false;
  xzBtn.classList.remove("talking");
  xzBtn.textContent = "📡 干杯助手";
  if (xzProcessor) { xzProcessor.disconnect(); xzProcessor = null; }
  if (xzAudioCtx) { xzAudioCtx.close().catch(() => {}); xzAudioCtx = null; }
  send({ type: "xiaozhi", action: "stop" });
  addLog("✅ 已松开，等待干杯助手回复…");
}

// 流式播放回复：每块到达立即排进 AudioContext 时钟，低延迟 + 无缝衔接
let xzPlayCtx = null;       // 播放用 AudioContext（与麦克风采集独立）
let xzNextStart = 0;        // 下一块应开始的时刻（AudioContext 时钟）
let xzPlayStarted = false;  // 是否已开始播第一块

function ensurePlayCtx() {
  if (xzPlayCtx) return true;
  try {
    xzPlayCtx = new (window.AudioContext || window.webkitAudioContext)();
    return true;
  } catch (e) {
    addLog("❌ 干杯助手播放初始化失败: " + e.message);
    return false;
  }
}

// 每块到达：立即解码 → 排到精确时刻播放（第一块立刻播，后续无缝接上）
function accumulateXiaozhiReply(b64) {
  if (!ensurePlayCtx()) return;
  try {
    const bin = atob(b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    const sr = 24000;
    const nSamples = bytes.length / 2;      // int16 = 2 字节
    if (nSamples <= 0) return;
    // 建 AudioBuffer（int16 → float32）
    const buf = xzPlayCtx.createBuffer(1, nSamples, sr);
    const ch = buf.getChannelData(0);
    for (let i = 0; i < nSamples; i++) {
      // 有符号 int16（小端）：先拼无符号，再转有符号
      let v = bytes[i * 2] | (bytes[i * 2 + 1] << 8);
      if (v >= 32768) v -= 65536;
      ch[i] = v / 32768;
    }
    // 调度：开始时刻 = 上一块结尾（或马上）
    const now = xzPlayCtx.currentTime;
    let when = xzNextStart > now ? xzNextStart : now + 0.02;  // 稍提前缓冲
    const src = xzPlayCtx.createBufferSource();
    src.buffer = buf;
    src.connect(xzPlayCtx.destination);
    src.start(when);
    xzNextStart = when + buf.duration;      // 下一块接在这块之后
    xzPlayStarted = true;
    if (!xzPlayCtx.listener && xzPlayCtx.resume) xzPlayCtx.resume().catch(() => {});
  } catch (e) {
    addLog("❌ 干杯助手回复解码失败: " + e.message);
  }
}

function flushXiaozhiReply() {
  // TTS 结束：本段对话播放完毕，重置时钟（下次对话重新起播）
  xzNextStart = 0;
  xzPlayStarted = false;
}

xzBtn.addEventListener("pointerdown", (e) => { e.preventDefault(); xzStart(); });
xzBtn.addEventListener("pointerup", xzStop);
xzBtn.addEventListener("pointerleave", xzStop);
xzBtn.addEventListener("touchstart", (e) => { e.preventDefault(); xzStart(); }, { passive: false });
xzBtn.addEventListener("touchend", xzStop);

// ================= 时钟 =================
setInterval(() => {
  $("clock").textContent = new Date().toLocaleTimeString("zh-CN", { hour12: false });
}, 1000);

addLog("🚗 干杯一号 小车端就绪");
