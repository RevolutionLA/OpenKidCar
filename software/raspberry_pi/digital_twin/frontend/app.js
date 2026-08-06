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
  // 只创建灯光材质；mesh 由 attachLightsToModel 挂到模型的车灯节点上
  headlightMat = new THREE.MeshStandardMaterial({ color: 0xffffff, emissive: 0xffffff, emissiveIntensity: 0 });
  brakeMat = new THREE.MeshStandardMaterial({ color: 0xff2020, emissive: 0xff2020, emissiveIntensity: 0 });
  stripMat = new THREE.MeshStandardMaterial({ color: 0x00ffff, emissive: 0x00ffff, emissiveIntensity: 0 });
  turnLMat = new THREE.MeshStandardMaterial({ color: 0xffaa00, emissive: 0xffaa00, emissiveIntensity: 0 });
  turnRMat = new THREE.MeshStandardMaterial({ color: 0xffaa00, emissive: 0xffaa00, emissiveIntensity: 0 });
}

// 把灯光 mesh 直接挂到模型的真实车灯节点上：
//  前灯/转向灯 → BodyHeadlights 节点，刹车灯 → BodyTaillights 节点
// 这样灯光跟模型车灯走，方向自动正确（不依赖任何方向假设）
function attachLightsToModel(model) {
  let headNode = null, tailNode = null;
  model.traverse(o => {
    if (o.isMesh) {
      const n = o.name.toLowerCase();
      if (n.includes("headlight") && !headNode) headNode = o;
      if (n.includes("taillight") && !tailNode) tailNode = o;
    }
  });
  if (headNode) {
    [[0.2, 0, 0], [-0.2, 0, 0]].forEach(p => {
      const l = new THREE.Mesh(new THREE.BoxGeometry(0.16, 0.08, 0.04), headlightMat);
      l.position.set(...p);
      headNode.add(l);
    });
    [[0.32, 0, 0], [-0.32, 0, 0]].forEach(p => {
      const t = new THREE.Mesh(new THREE.BoxGeometry(0.1, 0.06, 0.03), turnLMat);
      t.position.set(...p);
      headNode.add(t);
    });
    log("[灯光] 已挂接前大灯节点");
  } else {
    log("[灯光] 未找到前大灯节点");
  }
  if (tailNode) {
    const b = new THREE.Mesh(new THREE.BoxGeometry(0.8, 0.07, 0.04), brakeMat);
    tailNode.add(b);
    log("[灯光] 已挂接尾灯节点");
  }
  // 灯带：车身两侧（用模型包围盒自动定位，车头车尾都能亮）
  const box = new THREE.Box3().setFromObject(model);
  const size = box.getSize(new THREE.Vector3());
  const hw = size.x / 2;
  [[hw - 0.05, 0.1, 0], [-hw + 0.05, 0.1, 0]].forEach(p => {
    const s = new THREE.Mesh(new THREE.BoxGeometry(0.03, 0.05, size.z * 0.8), stripMat);
    s.position.set(...p);
    model.add(s);
  });
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
  // 模型原始方向即正确；灯光已按车头 +Z 直接定位（buildLights），无需旋转
  car: {},
};

// 让模型底部贴合地面（世界 y 最低点放到 y=0）
function sitOnGround(model) {
  model.updateMatrixWorld(true);
  const box = new THREE.Box3().setFromObject(model);
  model.position.y += -box.min.y;
}

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
      // 方向归一化：只有配置了旋转才应用；car 为空配置 → 保持模型原始方向
      if (cfg.rotX !== undefined || cfg.rotY !== undefined || cfg.rotZ !== undefined) {
        if (cfg.rotY) model.rotateY(cfg.rotY);
        if (cfg.rotX) model.rotateX(cfg.rotX);
        if (cfg.rotZ) model.rotateZ(cfg.rotZ);
      } else if (cfg.layFlat) {
        const box0 = new THREE.Box3().setFromObject(model);
        const s0 = box0.getSize(new THREE.Vector3());
        if (s0.y > s0.x && s0.y > s0.z) model.rotation.x = -Math.PI / 2;
      }
      // 统一适配：最长边 = 2.2
      const box = new THREE.Box3().setFromObject(model);
      const size = box.getSize(new THREE.Vector3());
      model.scale.setScalar(2.2 / Math.max(size.x, size.z));
      // 灯光挂到模型的真实车灯节点（方向自动对齐，不依赖任何假设）
      attachLightsToModel(model);
      // 收集轮子
      model.traverse(o => {
        if (o.isMesh) o.castShadow = true;
        // WheelFrontL/R、WheelRearL/R 是组（Group）不是 Mesh，不能只查 isMesh
        const n = o.name ? o.name.toLowerCase() : "";
        if (/^wheel(front|rear)[lr]$/.test(n)) {
          wheelNodes.push(o);
          if (n.includes("front")) frontWheels.push(o);
        }
      });
      log(`轮子节点: ${wheelNodes.length} 个，前轮: ${frontWheels.length} 个`);
      carGroup.add(model);
      sitOnGround(model);
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
let actx, engGain, hornGain, engineSrc = null, engineBuffer = null;
function initAudio() {
  if (actx) { actx.resume(); return; }
  try {
    actx = new (window.AudioContext || window.webkitAudioContext)();
    engGain = actx.createGain();
    engGain.gain.value = 0;
    engGain.connect(actx.destination);
    hornGain = actx.createGain();
    hornGain.gain.value = 0;
    hornGain.connect(actx.destination);
    // 加载真实赛车引擎样本（CC0 / Public Domain）
    loadEngineSound();
    // 鸣笛（合成双音；后续可换真实喇叭样本）
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

async function loadEngineSound() {
  try {
    const res = await fetch("assets/engine.mp3");
    const buf = await res.arrayBuffer();
    engineBuffer = await actx.decodeAudioData(buf);
    startEngineLoop();
  } catch (e) {
    console.log("引擎声样本加载失败:", e);
  }
}

function startEngineLoop() {
  if (engineSrc) { try { engineSrc.stop(); } catch (e) {} }
  engineSrc = actx.createBufferSource();
  engineSrc.buffer = engineBuffer;
  engineSrc.loop = true;
  engineSrc.playbackRate.value = 0.7;
  engineSrc.connect(engGain);
  engineSrc.start();
}

function updateEngine() {
  if (!actx) return;
  const t = car.throttle / 100;
  if (engineSrc) engineSrc.playbackRate.value = 0.7 + t * 1.4;   // 油门 → 转速
  const vol = car.mute || car.ebrk ? 0 : t * 0.55;
  engGain.gain.value += (vol - engGain.gain.value) * 0.08;        // 油门 0 → 无声
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
  const knob = document.getElementById("steer-knob");
  if (knob) knob.style.left = `calc(${(car.steer * 0.5 + 0.5) * 100}% - 8px)`;
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

  // 转向手柄：水平拖动把手转向（卡丁车式）
  const steerHandle = document.getElementById("steer-handle");
  const steerKnob = document.getElementById("steer-knob");
  let steerDrag = false;
  const setSteer = clientX => {
    const r = steerHandle.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (clientX - r.left) / r.width));
    const s = (ratio - 0.5) * 2;   // -1..1
    car.steer = s;                 // 本地即时生效，不等后端回传
    steerKnob.style.left = `calc(${ratio * 100}% - 8px)`;
    document.getElementById("steer-val").textContent = Math.round(s * 90) + "°";
    send({ type: "steer", value: s });
  };
  steerHandle.addEventListener("mousedown", e => { steerDrag = true; setSteer(e.clientX); });
  steerHandle.addEventListener("touchstart", e => { steerDrag = true; setSteer(e.touches[0].clientX); e.preventDefault(); });
  window.addEventListener("mouseup", () => { steerDrag = false; });
  window.addEventListener("touchend", () => { steerDrag = false; });
  const steerMove = e => {
    if (!steerDrag) return;
    setSteer(e.clientX !== undefined ? e.clientX : e.touches[0].clientX);
  };
  window.addEventListener("mousemove", steerMove);
  window.addEventListener("touchmove", e => { if (steerDrag) { e.preventDefault(); steerMove(e.touches[0]); } }, { passive: false });

  // 音频：第一次点击启用
  document.body.addEventListener("click", () => initAudio(), { capture: true });
  document.body.addEventListener("touchstart", () => initAudio(), { capture: true });

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
    .catch(e => {
      rec.textContent = "摄像头不可用";
      log("[摄像头] " + (e && e.message) + " —— 请允许权限/检查摄像头");
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
  // 家长按住说话（真实录音，松开回放给孩子）
  const pbtn = document.getElementById("parent-btn");
  let parentRec = null, parentChunks = [];
  const startParent = async () => {
    parentChunks = [];
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      parentRec = new MediaRecorder(stream);
      parentRec.ondataavailable = e => parentChunks.push(e.data);
      parentRec.onstop = () => {
        const blob = new Blob(parentChunks, { type: parentRec.mimeType || "audio/webm" });
        const a = new Audio(URL.createObjectURL(blob));
        a.play();
        status.textContent = "已发送给孩子 ✓";
        log("家长: 对讲语音已发送");
        stream.getTracks().forEach(t => t.stop());
        parentRec = null;
      };
      parentRec.start();
      status.textContent = "家长说话中…";
      log("家长: 按住说话中…");
    } catch (e) {
      status.textContent = "麦克风不可用";
      log("[对讲] 麦克风不可用: " + e.message);
    }
  };
  const stopParent = () => { if (parentRec && parentRec.state === "recording") parentRec.stop(); };
  pbtn.addEventListener("mousedown", startParent);
  pbtn.addEventListener("mouseup", stopParent);
  pbtn.addEventListener("mouseleave", stopParent);
  pbtn.addEventListener("touchstart", e => { e.preventDefault(); startParent(); });
  pbtn.addEventListener("touchend", stopParent);
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
