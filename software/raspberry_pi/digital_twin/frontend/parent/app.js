/* 干杯一号 · 家长端
   同一辆车的真实状态（WebSocket /ws_parent 直连大脑+小脑核心）。
   看 GPS / 电量 / 速度；对讲与视频帧通过 WS 与小车端互转。
*/
"use strict";

const $ = (id) => document.getElementById(id);
const wsUrl = (location.protocol === "https:" ? "wss" : "ws") + "://" + location.host + "/ws";
const HOME = { lat: 39.9087, lng: 116.3975 };

// ================= WebSocket =================
const ws = new WebSocket(wsUrl);

ws.onopen = () => setOnline(true);
ws.onclose = () => setOnline(false);
ws.onerror = () => setOnline(false);

ws.onmessage = (e) => {
  let m;
  try { m = JSON.parse(e.data); } catch { return; }
  if (m.type === "state") render(m.data);
  else if (m.type === "audio") playAudio(m.data);
  else if (m.type === "video") $("remote-video").src = m.data;
  else if (m.type === "call") startVideoCall();
  else if (m.type === "hangup") stopVideoCall();
};

function send(obj) {
  if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(obj));
}

function setOnline(on) {
  const chip = $("chip-online");
  chip.classList.toggle("on", on);
  chip.classList.toggle("off", !on);
  $("online-text").textContent = on ? "孩子在线" : "连接断开";
}

// ================= 状态渲染 =================
function render(s) {
  // 在线
  setOnline(s.online);

  // 车辆
  $("p-speed").textContent = Math.round(s.speed);
  $("p-gear").textContent = "D" + s.gear;
  $("p-throttle").textContent = Math.round(s.throttle) + "%";
  const ebrkEl = $("p-ebrk");
  ebrkEl.textContent = s.ebrk ? "触发！" : "正常";
  ebrkEl.className = s.ebrk ? "danger" : "safe";

  // GPS
  const g = s.gps;
  $("p-lat").textContent = g.lat.toFixed(6);
  $("p-lng").textContent = g.lng.toFixed(6);
  $("p-sat").textContent = g.sat;
  $("p-head").textContent = Math.round(g.heading) + "°";
  pushTrace(g);
  drawMap();

  // 电量
  const bat = Math.round(s.battery_pct);
  $("p-bat").textContent = bat + "%";
  const fill = $("bat-fill");
  fill.style.width = bat + "%";
  fill.classList.toggle("low", bat < 25);
  $("p-volt").textContent = s.voltage.toFixed(1) + " V";
  $("p-amp").textContent = s.current.toFixed(1) + " A";
  $("p-temp").textContent = Math.round(s.temp) + " ℃";
}

// ================= GPS 轨迹地图 =================
const trace = [];
const MAX_TRACE = 400;

function pushTrace(g) {
  const last = trace[trace.length - 1];
  if (last && Math.abs(last.lat - g.lat) < 1e-7 && Math.abs(last.lng - g.lng) < 1e-7) return;
  trace.push({ lat: g.lat, lng: g.lng, heading: g.heading });
  if (trace.length > MAX_TRACE) trace.shift();
}

function drawMap() {
  const cv = $("map");
  if (!trace.length) return;
  const ctx = cv.getContext("2d");
  const W = cv.width, H = cv.height;
  ctx.clearRect(0, 0, W, H);

  // 边界（含起点"家"）
  let minLat = HOME.lat, maxLat = HOME.lat, minLng = HOME.lng, maxLng = HOME.lng;
  for (const p of trace) {
    minLat = Math.min(minLat, p.lat); maxLat = Math.max(maxLat, p.lat);
    minLng = Math.min(minLng, p.lng); maxLng = Math.max(maxLng, p.lng);
  }
  const latR = Math.max(maxLat - minLat, 1e-6);
  const lngR = Math.max(maxLng - minLng, 1e-6);
  const cosLat = Math.cos((trace[trace.length - 1].lat * Math.PI) / 180);
  const padPx = 40;
  const scale = Math.min((W - padPx) / (lngR * cosLat), (H - padPx) / latR);
  const cLat = (minLat + maxLat) / 2, cLng = (minLng + maxLng) / 2;
  const X = (lng) => W / 2 + (lng - cLng) * cosLat * scale;
  const Y = (lat) => H / 2 - (lat - cLat) * scale;

  // 网格
  ctx.strokeStyle = "rgba(34,211,238,0.08)";
  ctx.lineWidth = 1;
  for (let i = 0; i <= 6; i++) {
    ctx.beginPath(); ctx.moveTo((W / 6) * i, 0); ctx.lineTo((W / 6) * i, H); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(0, (H / 6) * i); ctx.lineTo(W, (H / 6) * i); ctx.stroke();
  }

  // 轨迹
  if (trace.length > 1) {
    ctx.beginPath();
    ctx.strokeStyle = "rgba(34,211,238,0.75)";
    ctx.lineWidth = 2;
    ctx.shadowColor = "#22d3ee"; ctx.shadowBlur = 8;
    trace.forEach((p, i) => {
      const x = X(p.lng), y = Y(p.lat);
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });
    ctx.stroke();
    ctx.shadowBlur = 0;
  }

  // 家（起点）
  ctx.beginPath();
  ctx.fillStyle = "#71839b";
  ctx.arc(X(HOME.lng), Y(HOME.lat), 5, 0, Math.PI * 2);
  ctx.fill();
  ctx.font = "10px sans-serif";
  ctx.fillStyle = "#71839b";
  ctx.fillText("家", X(HOME.lng) + 8, Y(HOME.lat) - 6);

  // 当前位置 + 朝向箭头 + 脉冲圈
  const cur = trace[trace.length - 1];
  const cx = X(cur.lng), cy = Y(cur.lat);
  const pulse = ((Date.now() * 0.001) % 1) * 22 + 8;
  ctx.beginPath();
  ctx.strokeStyle = "rgba(52,211,153,0.35)";
  ctx.lineWidth = 2;
  ctx.arc(cx, cy, pulse, 0, Math.PI * 2);
  ctx.stroke();

  // 朝向箭头
  const a = (cur.heading * Math.PI) / 180;
  ctx.save();
  ctx.translate(cx, cy);
  ctx.rotate(a);
  ctx.beginPath();
  ctx.fillStyle = "#34d399";
  ctx.moveTo(12, 0); ctx.lineTo(-6, -7); ctx.lineTo(-6, 7); ctx.closePath();
  ctx.fill();
  ctx.restore();

  // 位置点
  ctx.beginPath();
  ctx.fillStyle = "#34d399";
  ctx.shadowColor = "#34d399"; ctx.shadowBlur = 10;
  ctx.arc(cx, cy, 5, 0, Math.PI * 2);
  ctx.fill();
  ctx.shadowBlur = 0;
}

// ================= 对讲（PTT 按住说话 → 小车端） =================
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
      reader.onload = () => send({ type: "audio", from: "parent", data: reader.result });
      reader.readAsDataURL(blob);
      recChunks = [];
    };
    return true;
  } catch {
    $("talk-hint").textContent = "⚠️ 无法使用麦克风";
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
  $("talk-hint").textContent = "正在对孩子说话…";
  recChunks = [];
  recorder.start();
});
ptt.addEventListener("pointerup", () => {
  if (!pttOn) return;
  pttOn = false;
  ptt.classList.remove("talking");
  $("talk-hint").textContent = "按住说话，孩子那边会响起对讲声";
  if (recorder.state !== "inactive") recorder.stop();
});
ptt.addEventListener("pointerleave", () => ptt.dispatchEvent(new Event("pointerup")));

function playAudio(dataUrl) {
  talkPlayer.src = dataUrl;
  talkPlayer.play().catch(() => {});
}

// ================= 视频（单向：只看小车端推送的画面） =================
let inCall = false;

function startVideoCall() {
  if (inCall) return;
  inCall = true;
  $("video-area").classList.remove("hidden");   // 显示视频窗格
  $("remote-empty").classList.add("hidden");
  $("call-state").textContent = "通话中";
  $("call-state").classList.add("live");
  $("btn-call").classList.add("hidden");
  $("btn-hangup").classList.remove("hidden");
  // 小车端收到 call 后自动推流，视频帧在 onmessage 里显示到 remote-video
}

function stopVideoCall() {
  if (!inCall) return;   // 已挂断，避免 hangup 循环转发
  inCall = false;
  $("video-area").classList.add("hidden");      // 隐藏视频窗格
  $("remote-video").src = "";
  $("remote-empty").classList.remove("hidden");
  $("call-state").textContent = "已挂断";
  $("call-state").classList.remove("live");
  $("btn-call").classList.remove("hidden");
  $("btn-hangup").classList.add("hidden");
  send({ type: "hangup" });
}

$("btn-call").addEventListener("click", () => {
  send({ type: "call" });
  startVideoCall();
});
$("btn-hangup").addEventListener("click", stopVideoCall);

// ================= 远程急刹 =================
$("btn-ebrk").addEventListener("click", () => {
  send({ type: "remote_ebrk" });
  const btn = $("btn-ebrk");
  btn.style.transform = "scale(0.98)";
  setTimeout(() => (btn.style.transform = ""), 120);
});

// ================= 时钟 =================
setInterval(() => {
  $("clock").textContent = new Date().toLocaleTimeString("zh-CN", { hour12: false });
}, 1000);
