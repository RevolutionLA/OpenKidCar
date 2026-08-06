/* ============================================================
 * 干杯一号 · 数字孪生驾驶舱 v3
 * 前端 ↔ WebSocket ↔ Python后端(Brain + CerebellumSim + vosk语音)
 * 状态全部来自后端大脑/小脑；操作全部发往后端。
 * ============================================================ */

// ================= 状态（由后端同步） =================
const car = {
  online: false, throttle: 0, brake: 0, gear: 2, steer: 0,
  light: false, mute: false, strip: false, horn: false, ebrk: false,
  speed: 0, motor: 0, turn: "off",
};
const GEAR_MAX = { 1: 10, 2: 15, 3: 20, 4: 25 };
const BTN_NAMES = {
  light: "LIGHT_BTN", mute: "MUTE_BTN", strip: "STRIP_BTN",
  horn: "HORN_BTN", ebrk: "EBRK_BTN",
};

// ================= WebSocket =================
let ws = null;
function connect() {
  ws = new WebSocket("ws://" + location.host + "/ws");
  ws.onopen = () => log("已连接：大脑 + 小脑在线");
  ws.onclose = () => { log("连接断开，5秒后重连…"); setTimeout(connect, 5000); };
  ws.onmessage = e => {
    const m = JSON.parse(e.data);
    if (m.type === "state") applyState(m.data);
    else if (m.type === "log") log(m.text);
  };
}
function send(obj) {
  if (ws && ws.readyState === 1) ws.send(JSON.stringify(obj));
}
function applyState(s) {
  Object.assign(car, s);
  car.turn = car.steer < -0.25 ? "L" : car.steer > 0.25 ? "R" : "off";
  updateHUD();
}

// ================= Three.js 场景 =================
let scene, camera, renderer, carGroup;
const wheels = [], frontWheels = [];
let headlightMat, brakeMat, stripMat, headLamp, turnLMat, turnRMat;

function initScene() {
  scene = new THREE.Scene();
  scene.fog = new THREE.Fog(0x05080d, 30, 70);
  camera = new THREE.PerspectiveCamera(50, innerWidth / innerHeight, 0.1, 100);
  renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setSize(innerWidth, innerHeight);
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.shadowMap.enabled = true;
  document.getElementById("scene").appendChild(renderer.domElement);

  scene.add(new THREE.AmbientLight(0x99aac8, 0.9));
  const dir = new THREE.DirectionalLight(0xffffff, 1.4);
  dir.position.set(6, 9, 5);
  dir.castShadow = true;
  scene.add(dir);
  const rim = new THREE.DirectionalLight(0x22d3ee, 0.5);
  rim.position.set(-5, 3, -4);
  scene.add(rim);

  const ground = new THREE.Mesh(
    new THREE.PlaneGeometry(80, 80),
    new THREE.MeshStandardMaterial({ color: 0x141c28, roughness: 0.9 })
  );
  ground.rotation.x = -Math.PI / 2;
  ground.receiveShadow = true;
  scene.add(ground);
  scene.add(new THREE.GridHelper(80, 40, 0x2a3a50, 0x1a2838));

  // 地面反光点（氛围）
  const glowLight = new THREE.PointLight(0x22d3ee, 0.8, 14);
  glowLight.position.set(0, 1.8, 0);
  scene.add(glowLight);

  headLamp = new THREE.SpotLight(0xffffff, 0, 25, Math.PI / 5, 0.4);
  headLamp.position.set(0, 0.5, -1.3);   // 车头朝 -Z
  headLamp.target.position.set(0, 0, -6);
  scene.add(headLamp);
  scene.add(headLamp.target);

  window.addEventListener("resize", () => {
    camera.aspect = innerWidth / innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(innerWidth, innerHeight);
  });
}

// ================= 3D 车模（ferrari GLB + 附加灯光 mesh） =================
let wheelNodes = [];   // 模型内 wheel_* 节点

let lightsGroup;

function buildLights() {
  // 灯光组挂在模型上（约定：车头朝 -Z，车长适配到约 2.2）
  lightsGroup = new THREE.Group();
  // 前灯
  headlightMat = new THREE.MeshStandardMaterial({ color: 0xffffff, emissive: 0xffffff, emissiveIntensity: 0 });
  [[0.4, 0.45, -1.05], [-0.4, 0.45, -1.05]].forEach(p => {
    const l = new THREE.Mesh(new THREE.BoxGeometry(0.24, 0.1, 0.04), headlightMat);
    l.position.set(...p);
    lightsGroup.add(l);
  });
  // 刹车灯
  brakeMat = new THREE.MeshStandardMaterial({ color: 0xff2020, emissive: 0xff2020, emissiveIntensity: 0 });
  const brakeBar = new THREE.Mesh(new THREE.BoxGeometry(0.9, 0.08, 0.04), brakeMat);
  brakeBar.position.set(0, 0.45, 1.05);
  lightsGroup.add(brakeBar);
  // 灯带
  stripMat = new THREE.MeshStandardMaterial({ color: 0x00ffff, emissive: 0x00ffff, emissiveIntensity: 0 });
  [[0.6, 0.28, 0], [-0.6, 0.28, 0]].forEach(p => {
    const s = new THREE.Mesh(new THREE.BoxGeometry(0.03, 0.04, 1.6), stripMat);
    s.position.set(...p);
    lightsGroup.add(s);
  });
  // 转向灯
  turnLMat = new THREE.MeshStandardMaterial({ color: 0xffaa00, emissive: 0xffaa00, emissiveIntensity: 0 });
  turnRMat = new THREE.MeshStandardMaterial({ color: 0xffaa00, emissive: 0xffaa00, emissiveIntensity: 0 });
  const tl = new THREE.Mesh(new THREE.BoxGeometry(0.18, 0.08, 0.04), turnLMat);
  tl.position.set(0.5, 0.45, -1.05);
  const tr = new THREE.Mesh(new THREE.BoxGeometry(0.18, 0.08, 0.04), turnRMat);
  tr.position.set(-0.5, 0.45, -1.05);
  lightsGroup.add(tl, tr);
}

let currentModel = null, currentModelName = null;

// 程序化卡丁车（车头朝 -Z，轮子朝向正确，灯光/转向联动正常）
function buildProceduralKart() {
  currentModel = new THREE.Group();
  const bodyMat = new THREE.MeshStandardMaterial({ color: 0x3d6bff, metalness: 0.5, roughness: 0.25 });
  const darkMat = new THREE.MeshStandardMaterial({ color: 0x1a2230, metalness: 0.5, roughness: 0.6 });
  const accentMat = new THREE.MeshStandardMaterial({ color: 0xffc422, metalness: 0.8, roughness: 0.2 });
  const glassMat = new THREE.MeshPhysicalMaterial({
    color: 0x9fd8ff, transparent: true, opacity: 0.4, roughness: 0.05, metalness: 0.1,
  });

  // 底盘（宽 X × 长 Z，车头 -Z）
  const chassis = new THREE.Mesh(new THREE.BoxGeometry(1.05, 0.16, 1.9), darkMat);
  chassis.position.y = 0.24;
  // 车身（Extrude：X=宽, Y=长→世界 Z，车头在 -Z）
  const shape = new THREE.Shape();
  shape.moveTo(0, -0.98);
  shape.quadraticCurveTo(0.38, -0.62, 0.46, -0.05);
  shape.quadraticCurveTo(0.52, 0.58, 0.44, 0.92);
  shape.lineTo(-0.44, 0.92);
  shape.quadraticCurveTo(-0.52, 0.58, -0.46, -0.05);
  shape.quadraticCurveTo(-0.38, -0.62, 0, -0.98);
  const body = new THREE.Mesh(new THREE.ExtrudeGeometry(shape, {
    depth: 0.34, bevelEnabled: true, bevelThickness: 0.05, bevelSize: 0.04, bevelSegments: 4,
  }), bodyMat);
  body.rotation.x = -Math.PI / 2;
  body.position.y = 0.5;

  // 尾翼（车尾 +Z）
  const wing = new THREE.Mesh(new THREE.BoxGeometry(1.3, 0.07, 0.34), accentMat);
  wing.position.set(0, 0.98, 0.9);
  [[0, 0.6, 0.72], [0.45, 0.6, 0.72], [-0.45, 0.6, 0.72]].forEach(p => {
    const post = new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.5, 0.05), darkMat);
    post.position.set(...p);
    currentModel.add(post);
  });
  // 防滚架（车尾上方）
  const rollbar = new THREE.Mesh(new THREE.TorusGeometry(0.18, 0.035, 8, 18, Math.PI), darkMat);
  rollbar.position.set(0, 0.95, 0.5);
  rollbar.rotation.y = Math.PI / 2;
  rollbar.rotation.z = Math.PI;
  // 挡风玻璃（车头 -Z 附近）
  const glass = new THREE.Mesh(new THREE.BoxGeometry(0.72, 0.3, 0.03), glassMat);
  glass.position.set(0, 0.8, -0.35);
  glass.rotation.x = 0.35;
  // 座椅（中部）
  const seat = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.45, 0.5), darkMat);
  seat.position.set(0, 0.68, 0.1);
  const seatBack = new THREE.Mesh(new THREE.BoxGeometry(0.55, 0.75, 0.14), darkMat);
  seatBack.position.set(0, 0.9, 0.4);
  // 方向盘（中前，朝驾驶位）
  const steer = new THREE.Mesh(new THREE.TorusGeometry(0.14, 0.035, 8, 20), darkMat);
  steer.position.set(0, 0.72, -0.28);
  steer.rotation.x = Math.PI / 2.6;

  // 车轮（X 左右 × Z 前后，车头 -Z；轴沿 X=车宽，朝向正确）
  const tireMat = new THREE.MeshStandardMaterial({ color: 0x0b0d12, roughness: 0.95 });
  [[-0.62, 0.55], [0.62, 0.55], [-0.62, -0.55], [0.62, -0.55]].forEach(([x, z], idx) => {
    const w = new THREE.Group();
    w.userData.isWheel = true;
    w.userData.isFront = z < 0;   // 车头 -Z
    const tire = new THREE.Mesh(new THREE.CylinderGeometry(0.3, 0.3, 0.2, 24), tireMat);
    tire.rotation.z = Math.PI / 2;
    const hub = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.12, 0.22, 8), accentMat);
    hub.rotation.z = Math.PI / 2;
    w.add(tire, hub);
    w.position.set(x, 0.3, z);
    currentModel.add(w);
  });

  currentModel.add(chassis, body, wing, rollbar, glass, seat, seatBack, steer);
  currentModel.position.y = 0.1;
  currentModel.traverse(o => { if (o.isMesh) o.castShadow = true; });
  currentModel.add(lightsGroup);
  carGroup.add(currentModel);
  // 收集轮子
  wheelNodes.length = 0; frontWheels.length = 0;
  currentModel.traverse(o => {
    if (o.userData.isWheel) {
      wheelNodes.push(o);
      if (o.userData.isFront) frontWheels.push(o);
    }
  });
  currentModelName = "standard";
  log("已显示卡丁车");
}

const MODEL_CONFIG = {
  // Khronos CarConcept：只需绕 Z 转 +90°。
  //  车长 Y→X（横着）、车宽 X→Y（轮子轴转到垂直左右→正常立着）、车高 Z→不变
  //  车头 -Y → +X（朝屏幕右）。若想朝左，改 rotZ 为 -PI/2。
  car: { rotZ: Math.PI / 2 },
};

function loadModel(name) {
  if (currentModel) carGroup.remove(currentModel);
  wheelNodes.length = 0;   // frontWheels 是 const，只能清空
  frontWheels.length = 0;
  const loader = new THREE.GLTFLoader();
  loader.load(
    "vendor/" + name + ".glb",
    gltf => {
      const model = gltf.scene;
      const cfg = MODEL_CONFIG[name] || {};
      // 方向归一化：优先用模型配置（rotateX/Y/Z 顺序明确），否则长轴是 Y 时躺平
      if (cfg.rotX !== undefined || cfg.rotY !== undefined || cfg.rotZ !== undefined) {
        if (cfg.rotX) model.rotateX(cfg.rotX);
        if (cfg.rotY) model.rotateY(cfg.rotY);
        if (cfg.rotZ) model.rotateZ(cfg.rotZ);
      } else {
        const box0 = new THREE.Box3().setFromObject(model);
        const s0 = box0.getSize(new THREE.Vector3());
        if (s0.y > s0.x && s0.y > s0.z) model.rotation.x = -Math.PI / 2;
      }
      // 统一适配：最长边 = 2.2，贴地
      const box = new THREE.Box3().setFromObject(model);
      const size = box.getSize(new THREE.Vector3());
      model.scale.setScalar(2.2 / Math.max(size.x, size.z));
      const b2 = new THREE.Box3().setFromObject(model);
      model.position.y = -b2.min.y;
      // 灯光挂在模型上（跟随翻转/缩放）
      model.add(lightsGroup);
      // 收集轮子
      model.traverse(o => {
        if (o.isMesh) {
          o.castShadow = true;
          const n = o.name.toLowerCase();
          // 精确匹配 WheelFrontL/R、WheelRearL/R（排除 Rim/Disc/Pad/方向盘）
          if (/^wheel(front|rear)[lr]$/.test(n)) {
            wheelNodes.push(o);
            if (n.includes("front")) frontWheels.push(o);
          }
        }
      });
      carGroup.add(model);
      currentModel = model;
      currentModelName = name;
      log("已加载模型: " + name);
      if (wheelNodes.length === 0) log("该模型无独立轮子节点，整体模拟");
    },
    undefined,
    err => log("模型加载失败: " + (err && err.message))
  );
}

// ================= 灯光联动 =================
function updateVisuals() {
  const braking = car.brake > 10 || car.ebrk;
  headlightMat.emissiveIntensity = car.light ? 1.2 : 0;
  headLamp.intensity = car.light ? 1.6 : 0;
  brakeMat.emissiveIntensity = braking ? 1.6 : 0;
  stripMat.emissiveIntensity = car.strip ? 1.2 : 0;
  if (car.strip) stripMat.emissive.setHSL(((Date.now() / 200) % 360) / 360, 1, 0.5);
  const blink = Math.floor(Date.now() / 250) % 2 === 0;
  turnLMat.emissiveIntensity = car.turn === "L" && blink ? 1.4 : 0;
  turnRMat.emissiveIntensity = car.turn === "R" && blink ? 1.4 : 0;
}

// ================= 车动画（基于后端状态） =================
function updateCar(dt) {
  const t = Date.now() / 1000;
  wheelNodes.forEach(w => (w.rotation.x += car.speed * dt * 3.2));
  carGroup.position.y = 0.05 + Math.sin(t * 30) * car.speed * 0.0022;
  carGroup.rotation.z = Math.sin(t * 18) * car.speed * 0.0016;
  carGroup.rotation.x = Math.sin(t * 26) * car.speed * 0.0009;
  carGroup.rotation.y = car.steer * 0.45;
  frontWheels.forEach(w => (w.rotation.y = car.steer * 0.6));
  updateVisuals();
}

// ================= 引擎声 + 喇叭（Web Audio） =================
let actx, engGain, engFilter, osc1, osc2, noiseGain, hornGain;
function initAudio() {
  if (actx) { actx.resume(); return; }
  try {
    actx = new (window.AudioContext || window.webkitAudioContext)();
    engGain = actx.createGain();
    engGain.gain.value = 0;
    engGain.connect(actx.destination);
    engFilter = actx.createBiquadFilter();
    engFilter.type = "lowpass";
    engFilter.frequency.value = 500;
    engFilter.connect(engGain);

    osc1 = actx.createOscillator();
    osc1.type = "sawtooth";
    osc1.frequency.value = 45;
    osc1.connect(engFilter);
    osc1.start();
    osc2 = actx.createOscillator();
    osc2.type = "square";
    osc2.frequency.value = 22;
    osc2.connect(engFilter);
    osc2.start();

    const buf = actx.createBuffer(1, actx.sampleRate * 2, actx.sampleRate);
    const d = buf.getChannelData(0);
    for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
    const noise = actx.createBufferSource();
    noise.buffer = buf;
    noise.loop = true;
    const nf = actx.createBiquadFilter();
    nf.type = "bandpass";
    nf.frequency.value = 140;
    nf.Q.value = 0.8;
    noiseGain = actx.createGain();
    noiseGain.gain.value = 0;
    noise.connect(nf); nf.connect(noiseGain); noiseGain.connect(engGain);
    noise.start();

    hornGain = actx.createGain();
    hornGain.gain.value = 0;
    hornGain.connect(actx.destination);
    [520, 660].forEach(f => {
      const h = actx.createOscillator();
      h.type = "square";
      h.frequency.value = f;
      h.connect(hornGain);
      h.start();
    });
  } catch (e) {
    console.log("音频初始化失败:", e);
  }
}

function updateEngine() {
  if (!actx) return;
  const t = car.throttle / 100;
  const rpm = 45 + t * 240;
  osc1.frequency.value = rpm;
  osc2.frequency.value = rpm * 0.5;
  engFilter.frequency.value = 350 + t * 1600;
  const vol = car.mute || car.ebrk ? 0 : 0.07 + t * 0.26;
  engGain.gain.value += (vol - engGain.gain.value) * 0.08;
  noiseGain.gain.value = t * 0.07;
  hornGain.gain.value = car.horn && !car.mute ? 0.09 : 0;
}

// ================= HUD 同步 =================
function updateHUD() {
  document.querySelectorAll(".ctrl[data-key]").forEach(b => {
    b.classList.toggle("on", !!car[b.dataset.key]);
  });
  document.querySelectorAll(".gear").forEach(b => {
    b.classList.toggle("active", +b.dataset.g === car.gear);
  });
  document.getElementById("gear-label").textContent = "档位 " + car.gear;
  document.getElementById("speed-num").textContent = Math.round(car.speed);
  ["throttle", "brake"].forEach(id => {
    const el = document.getElementById(id);
    el.style.setProperty("--pedal", car[id] + "%");
    el.querySelector(".p-val").textContent = Math.round(car[id]) + "%";
  });
  const wheelEl = document.getElementById("wheel");
  wheelEl.style.transform = `rotate(${(car.steer * 90).toFixed(0)}deg)`;
  document.getElementById("steer-val").textContent = Math.round(car.steer * 90) + "°";
  const sb = document.getElementById("status-brain");
  sb.textContent = car.online ? "大脑 ● 在线 · 小脑在线" : "大脑 ● 连接中";
  sb.style.color = car.online ? "var(--green)" : "var(--yellow)";
}

function log(msg) {
  const el = document.getElementById("log");
  el.innerHTML = msg + "<br>" + el.innerHTML;
  if (el.children.length > 6) el.removeChild(el.lastChild);
}

// ================= 交互（全部发往后端） =================
function bindControls() {
  // 中控按钮（喇叭单独按住处理）
  document.querySelectorAll(".ctrl[data-key]").forEach(btn => {
    if (btn.dataset.key === "horn") {
      btn.addEventListener("mousedown", () => send({ type: "horn", value: true }));
      btn.addEventListener("mouseup", () => send({ type: "horn", value: false }));
      btn.addEventListener("mouseleave", () => send({ type: "horn", value: false }));
      btn.addEventListener("touchstart", e => { e.preventDefault(); send({ type: "horn", value: true }); });
      btn.addEventListener("touchend", () => send({ type: "horn", value: false }));
      return;
    }
    btn.addEventListener("click", () => {
      send({ type: "btn", name: BTN_NAMES[btn.dataset.key] });
      if (btn.dataset.key === "ebrk") log("⚠️ 急刹请求已发送");
    });
  });

  document.querySelectorAll(".gear").forEach(b => {
    b.addEventListener("click", () => {
      send({ type: "gear", value: +b.dataset.g });
      log(`换档 -> ${b.dataset.g} 档`);
    });
  });

  // 语音
  document.getElementById("btn-voice").addEventListener("click", () => {
    send({ type: "voice" });
    document.getElementById("btn-voice").classList.add("flash");
    setTimeout(() => document.getElementById("btn-voice").classList.remove("flash"), 800);
  });

  // 踏板
  ["throttle", "brake"].forEach(id => {
    const el = document.getElementById(id);
    const apply = clientY => {
      const r = el.getBoundingClientRect();
      const v = Math.max(0, Math.min(100, Math.round((r.bottom - clientY) / r.height * 100)));
      send({ type: id, value: v });
    };
    const down = e => { el._drag = true; apply(e.clientY); };
    const move = e => { if (el._drag) apply(e.clientY); };
    const up = () => { el._drag = false; };
    el.addEventListener("mousedown", down);
    el.addEventListener("touchstart", e => down(e.touches[0]));
    window.addEventListener("mousemove", move);
    window.addEventListener("touchmove", e => { if (el._drag) { e.preventDefault(); move(e.touches[0]); } }, { passive: false });
    window.addEventListener("mouseup", up);
    window.addEventListener("touchend", up);
  });

  // 方向盘
  const wheelEl = document.getElementById("wheel");
  let steerDrag = false, steerLast = 0;
  wheelEl.addEventListener("mousedown", e => { steerDrag = true; steerLast = e.clientX; });
  wheelEl.addEventListener("touchstart", e => { steerDrag = true; steerLast = e.touches[0].clientX; e.preventDefault(); });
  window.addEventListener("mouseup", () => { steerDrag = false; });
  window.addEventListener("touchend", () => { steerDrag = false; });
  const steerMove = e => {
    if (!steerDrag) return;
    const x = e.clientX !== undefined ? e.clientX : e.touches[0].clientX;
    const dx = x - steerLast;
    steerLast = x;
    const s = Math.max(-1, Math.min(1, car.steer + dx * 0.035));
    send({ type: "steer", value: s });
  };
  window.addEventListener("mousemove", steerMove);
  window.addEventListener("touchmove", e => { if (steerDrag) { e.preventDefault(); steerMove(e.touches[0]); } }, { passive: false });

  // 音频：第一次点击启用
  document.body.addEventListener("click", () => initAudio(), { capture: true });
  document.body.addEventListener("touchstart", () => initAudio(), { capture: true });

  // 翻转朝向（灯光跟随模型一起翻转；headLamp 也同步反转）
  document.getElementById("flip-btn").addEventListener("click", () => {
    if (currentModel) {
      currentModel.rotation.y += Math.PI;
      headLamp.position.z *= -1;
      headLamp.target.position.z *= -1;
      log("已翻转朝向");
    }
  });
  log("👆 点击画面任意处启用声音");
}

// ================= 真实摄像头 =================
function initCamera() {
  const cam = document.getElementById("cam");
  const rec = document.getElementById("cam-rec");
  navigator.mediaDevices.getUserMedia({ video: { facingMode: "user" } })
    .then(stream => {
      cam.srcObject = stream;
      rec.textContent = "● REC";
      log("[摄像头] 已连接");
    })
    .catch(() => {
      rec.textContent = "摄像头不可用";
      log("[摄像头] 无法访问（可能无摄像头或无权限）");
    });
  document.getElementById("cam-flip").addEventListener("click", () => {
    cam.classList.toggle("flip");
    document.getElementById("cam-mode").textContent =
      cam.classList.contains("flip") ? "自拍 · VLOG" : "前视 · 行车记录";
  });
}

// ================= 对讲（真实录音 + 回放） =================
function speak(text) {
  try {
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "zh-CN";
    const voices = speechSynthesis.getVoices();
    const zh = voices.find(v => v.lang.includes("zh"));
    if (zh) u.voice = zh;
    speechSynthesis.speak(u);
  } catch (e) { console.log(e); }
}

function initTalk() {
  const btn = document.getElementById("talk-btn");
  const status = document.getElementById("talk-status");
  let recorder = null, chunks = [];
  const startRec = async () => {
    chunks = [];
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      recorder = new MediaRecorder(stream);
      recorder.ondataavailable = e => chunks.push(e.data);
      recorder.onstop = () => {
        const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
        const a = new Audio(URL.createObjectURL(blob));
        a.play();
        status.textContent = "已发送给家长 ✓";
        log("孩子: 对讲语音已发送");
        stream.getTracks().forEach(t => t.stop());
        recorder = null;
      };
      recorder.start();
      status.textContent = "对讲中… 请说话";
      log("孩子: 按住说话中…");
    } catch (e) {
      status.textContent = "麦克风不可用";
      log("[对讲] 麦克风不可用: " + e.message);
    }
  };
  const stopRec = () => { if (recorder && recorder.state === "recording") recorder.stop(); };
  btn.addEventListener("mousedown", startRec);
  btn.addEventListener("mouseup", stopRec);
  btn.addEventListener("mouseleave", stopRec);
  btn.addEventListener("touchstart", e => { e.preventDefault(); startRec(); });
  btn.addEventListener("touchend", stopRec);
  document.getElementById("parent-btn").addEventListener("click", () => {
    status.textContent = "家长发来语音";
    log("家长: 发来一条语音");
    speak("宝宝，注意安全，爸爸在看着你");
  });
}

// ================= 视角轨道 =================
let yaw = 0.6, pitch = 0.42, orbitDrag = false, lastMX = 0, lastMY = 0;
function updateOrbit() {
  const r = 4.4;
  camera.position.set(
    r * Math.cos(pitch) * Math.sin(yaw),
    r * Math.sin(pitch) + 0.9,
    r * Math.cos(pitch) * Math.cos(yaw)
  );
  camera.lookAt(0, 0.35, 0);
}
function bindOrbit() {
  const c = document.getElementById("scene");
  c.addEventListener("mousedown", e => { orbitDrag = true; lastMX = e.clientX; lastMY = e.clientY; });
  window.addEventListener("mouseup", () => { orbitDrag = false; });
  window.addEventListener("mousemove", e => {
    if (!orbitDrag) return;
    yaw += (e.clientX - lastMX) * 0.008;
    pitch = Math.max(0.05, Math.min(1.3, pitch + (e.clientY - lastMY) * 0.008));
    lastMX = e.clientX; lastMY = e.clientY;
  });
}

// ================= 主循环 =================
let lastT = performance.now();
function animate() {
  requestAnimationFrame(animate);
  const now = performance.now();
  const dt = Math.min(0.05, (now - lastT) / 1000);
  lastT = now;
  updateCar(dt);
  updateEngine();
  updateOrbit();
  renderer.render(scene, camera);
}

// ================= 数据面板 =================
setInterval(() => {
  document.getElementById("d-volt").textContent = (24.6 - car.throttle * 0.008).toFixed(1);
  document.getElementById("d-temp").textContent = Math.round(32 + car.speed * 0.2);
  document.getElementById("d-amp").textContent = (car.throttle * 0.05).toFixed(1);
  document.getElementById("d-state").textContent = car.speed > 0 ? "行驶中" : "静止";
}, 100);

// ================= 启动 =================
initScene();
carGroup = new THREE.Group();
buildLights();
scene.add(carGroup);
loadModel("car");
bindControls();
bindOrbit();
initCamera();
initTalk();
updateOrbit();
animate();
connect();
log("干杯一号 数字孪生启动，正在连接大脑+小脑…");
log("正在加载车模…");
