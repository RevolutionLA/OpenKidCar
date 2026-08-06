/* ============================================================
 * 干杯一号 · 数字孪生驾驶舱 v2
 * 3D 卡丁车（原地模拟）+ 灯光联动 + 方向盘/转向灯 + 真实摄像头
 * + 录音对讲 + Web Audio 引擎声/喇叭
 * ============================================================ */

// ================= 仿真状态 =================
const car = {
  throttle: 0, brake: 0, gear: 2,
  light: false, mute: false, strip: false, horn: false, ebrk: false,
  steer: 0, turn: "off",          // steer: -1..1, turn: L/R/off
  speed: 0,
};
const GEAR_MAX = { 1: 10, 2: 15, 3: 20, 4: 25 };

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

  scene.add(new THREE.AmbientLight(0x3a4a5c, 0.55));
  const dir = new THREE.DirectionalLight(0xffffff, 0.9);
  dir.position.set(6, 9, 5);
  dir.castShadow = true;
  scene.add(dir);
  const rim = new THREE.DirectionalLight(0x22d3ee, 0.25);
  rim.position.set(-5, 3, -4);
  scene.add(rim);

  const ground = new THREE.Mesh(
    new THREE.PlaneGeometry(80, 80),
    new THREE.MeshStandardMaterial({ color: 0x0a1018, roughness: 0.95 })
  );
  ground.rotation.x = -Math.PI / 2;
  ground.receiveShadow = true;
  scene.add(ground);
  scene.add(new THREE.GridHelper(80, 40, 0x1a2a3a, 0x12202e));

  headLamp = new THREE.SpotLight(0xffffff, 0, 25, Math.PI / 5, 0.4);
  headLamp.position.set(0, 0.5, 1.3);
  headLamp.target.position.set(0, 0, 6);
  scene.add(headLamp);
  scene.add(headLamp.target);

  window.addEventListener("resize", () => {
    camera.aspect = innerWidth / innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(innerWidth, innerHeight);
  });
}

// ================= 3D 卡丁车模型 =================
function buildCar() {
  carGroup = new THREE.Group();
  const bodyMat = new THREE.MeshStandardMaterial({ color: 0x1e4fd8, metalness: 0.6, roughness: 0.3 });
  const darkMat = new THREE.MeshStandardMaterial({ color: 0x161c26, metalness: 0.5, roughness: 0.6 });
  const accentMat = new THREE.MeshStandardMaterial({ color: 0xfbbf24, metalness: 0.7, roughness: 0.2 });

  // ---- 底盘 ----
  const under = new THREE.Mesh(new THREE.BoxGeometry(1.8, 0.1, 1.0), darkMat);
  under.position.y = 0.14;
  const chassis = new THREE.Mesh(new THREE.BoxGeometry(1.7, 0.18, 0.9), darkMat);
  chassis.position.y = 0.26;

  // ---- 车身 ----
  const main = new THREE.Mesh(new THREE.BoxGeometry(1.5, 0.34, 0.82), bodyMat);
  main.position.set(-0.05, 0.5, 0);
  // 前鼻（两层堆出楔形）
  const nose1 = new THREE.Mesh(new THREE.BoxGeometry(0.55, 0.22, 0.66), bodyMat);
  nose1.position.set(0.98, 0.44, 0);
  const nose2 = new THREE.Mesh(new THREE.BoxGeometry(0.32, 0.13, 0.5), bodyMat);
  nose2.position.set(1.3, 0.32, 0);

  // ---- 尾翼 ----
  const wing = new THREE.Mesh(new THREE.BoxGeometry(1.3, 0.08, 0.34), accentMat);
  wing.position.set(-0.85, 0.98, 0);
  [[-0.85, 0.6, 0.2], [-0.85, 0.6, -0.2]].forEach(p => {
    const post = new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.55, 0.05), darkMat);
    post.position.set(...p);
    carGroup.add(post);
  });

  // ---- 防滚架 ----
  const rollbar = new THREE.Mesh(new THREE.TorusGeometry(0.2, 0.03, 8, 18, Math.PI), darkMat);
  rollbar.position.set(-0.55, 0.82, 0);
  rollbar.rotation.y = Math.PI / 2;
  rollbar.rotation.z = Math.PI;

  // ---- 排气管 ----
  const exhaust = new THREE.Mesh(new THREE.CylinderGeometry(0.045, 0.045, 0.5, 10), darkMat);
  exhaust.rotation.x = Math.PI / 2;
  exhaust.position.set(0.65, 0.3, -0.46);

  // ---- 座椅 + 头枕 ----
  const seat = new THREE.Mesh(new THREE.BoxGeometry(0.45, 0.4, 0.42), darkMat);
  seat.position.set(-0.25, 0.62, 0.06);
  const seatBack = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.72, 0.1), darkMat);
  seatBack.position.set(-0.4, 0.82, -0.22);
  const headrest = new THREE.Mesh(new THREE.BoxGeometry(0.28, 0.24, 0.12), darkMat);
  headrest.position.set(-0.48, 1.15, -0.2);

  // ---- 方向盘 ----
  const steer = new THREE.Mesh(new THREE.TorusGeometry(0.14, 0.035, 8, 20), darkMat);
  steer.position.set(0.55, 0.7, 0.14);
  steer.rotation.x = Math.PI / 2.6;

  // ---- 车轮（带轮毂），前轮单独记录用于转向 ----
  const tireMat = new THREE.MeshStandardMaterial({ color: 0x0b0d12, roughness: 0.95 });
  const hubMat = accentMat;
  [[-0.65, 0.52], [0.65, 0.52], [-0.65, -0.52], [0.65, -0.52]].forEach(([x, z], idx) => {
    const w = new THREE.Group();
    const tire = new THREE.Mesh(new THREE.CylinderGeometry(0.3, 0.3, 0.2, 22), tireMat);
    tire.rotation.z = Math.PI / 2;
    const hub = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.12, 0.22, 8), hubMat);
    hub.rotation.z = Math.PI / 2;
    w.add(tire, hub);
    w.position.set(x, 0.3, z);
    wheels.push(w);
    if (idx < 2) frontWheels.push(w);
  });

  // ---- 前灯 ----
  headlightMat = new THREE.MeshStandardMaterial({ color: 0xffffff, emissive: 0xffffff, emissiveIntensity: 0 });
  [[0.55, 0.5, 0.43], [-0.55, 0.5, 0.43]].forEach(([x, y, z]) => {
    const l = new THREE.Mesh(new THREE.BoxGeometry(0.3, 0.15, 0.05), headlightMat);
    l.position.set(x, y, z);
    carGroup.add(l);
  });

  // ---- 刹车灯 ----
  brakeMat = new THREE.MeshStandardMaterial({ color: 0xff2020, emissive: 0xff2020, emissiveIntensity: 0 });
  const brakeBar = new THREE.Mesh(new THREE.BoxGeometry(1.15, 0.13, 0.05), brakeMat);
  brakeBar.position.set(0, 0.6, -0.46);
  carGroup.add(brakeBar);

  // ---- 灯带 ----
  stripMat = new THREE.MeshStandardMaterial({ color: 0x00ffff, emissive: 0x00ffff, emissiveIntensity: 0 });
  [[0.79, 0], [-0.79, 0]].forEach(([x, z]) => {
    const s = new THREE.Mesh(new THREE.BoxGeometry(0.04, 0.05, 0.95), stripMat);
    s.position.set(x, 0.46, z);
    carGroup.add(s);
  });

  // ---- 转向灯（前轮上方，黄色）----
  turnLMat = new THREE.MeshStandardMaterial({ color: 0xffaa00, emissive: 0xffaa00, emissiveIntensity: 0 });
  turnRMat = new THREE.MeshStandardMaterial({ color: 0xffaa00, emissive: 0xffaa00, emissiveIntensity: 0 });
  const turnL = new THREE.Mesh(new THREE.BoxGeometry(0.24, 0.1, 0.05), turnLMat);
  turnL.position.set(0.7, 0.5, 0.43);
  const turnR = new THREE.Mesh(new THREE.BoxGeometry(0.24, 0.1, 0.05), turnRMat);
  turnR.position.set(-0.7, 0.5, 0.43);
  carGroup.add(turnL, turnR);

  carGroup.add(under, chassis, main, nose1, nose2, wing, rollbar, exhaust,
               seat, seatBack, headrest, steer, ...wheels);
  carGroup.position.y = 0.15;
  scene.add(carGroup);
}

// ================= 灯光联动 =================
function updateVisuals() {
  const braking = car.brake > 10 || car.ebrk;
  headlightMat.emissiveIntensity = car.light ? 1.2 : 0;
  headLamp.intensity = car.light ? 1.6 : 0;
  brakeMat.emissiveIntensity = braking ? 1.6 : 0;
  stripMat.emissiveIntensity = car.strip ? 1.2 : 0;
  if (car.strip) {
    const hue = (Date.now() / 200) % 360;
    stripMat.emissive.setHSL(hue / 360, 1, 0.5);
  }
  // 转向灯闪烁
  const blink = Math.floor(Date.now() / 250) % 2 === 0;
  turnLMat.emissiveIntensity = (car.turn === "L" && blink) ? 1.4 : 0;
  turnRMat.emissiveIntensity = (car.turn === "R" && blink) ? 1.4 : 0;
}

// ================= 车运动（原地模拟） =================
function updateCar(dt) {
  const max = GEAR_MAX[car.gear];
  if (car.ebrk) car.speed *= 0.9;
  else if (car.brake > 10) car.speed *= Math.max(0, 1 - 2.5 * dt);
  else {
    const target = (car.throttle / 100) * max;
    car.speed += (target - car.speed) * Math.min(1, dt * 2.5);
  }
  car.speed = Math.max(0, Math.min(max, car.speed));

  // 原地模拟：轮子转 + 行驶震动 + 起伏（车不平移）
  wheels.forEach(w => (w.rotation.x += car.speed * dt * 3.2));
  const t = Date.now() / 1000;
  carGroup.position.y = 0.15 + Math.sin(t * 30) * car.speed * 0.0022;
  carGroup.rotation.z = Math.sin(t * 18) * car.speed * 0.0016;
  carGroup.rotation.x = Math.sin(t * 26) * car.speed * 0.0009;

  // 转向：车身偏转 + 前轮转向
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
    osc1.frequency.value = 40;
    osc1.connect(engFilter);
    osc1.start();
    osc2 = actx.createOscillator();
    osc2.type = "square";
    osc2.frequency.value = 20;
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

    // 喇叭（双音鸣笛）
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
  const vol = car.mute || car.ebrk ? 0 : 0.04 + t * 0.24;
  engGain.gain.value += (vol - engGain.gain.value) * 0.08;
  noiseGain.gain.value = t * 0.07;
  // 喇叭
  hornGain.gain.value = car.horn && !car.mute ? 0.09 : 0;
}

// ================= HUD 交互 =================
function log(msg) {
  const el = document.getElementById("log");
  el.innerHTML = msg + "<br>" + el.innerHTML;
  if (el.children.length > 6) el.removeChild(el.lastChild);
}

function bindControls() {
  document.querySelectorAll(".ctrl[data-key]").forEach(btn => {
    btn.addEventListener("click", () => {
      const k = btn.dataset.key;
      car[k] = !car[k];
      btn.classList.toggle("on", car[k]);
      const names = { light: "大灯", mute: "静音", strip: "灯带", horn: "喇叭", ebrk: "急刹" };
      log(`${names[k]} -> ${car[k] ? "开" : "关"}`);
      if (k === "ebrk" && car[k]) {
        log("⚠️ 急刹触发！");
        setTimeout(() => { car.ebrk = false; btn.classList.remove("on"); }, 1200);
      }
    });
  });

  document.querySelectorAll(".gear").forEach(b => {
    b.addEventListener("click", () => {
      car.gear = +b.dataset.g;
      document.querySelectorAll(".gear").forEach(x => x.classList.toggle("active", x === b));
      document.getElementById("gear-label").textContent = `档位 ${car.gear}`;
      log(`换档 -> ${car.gear} 档`);
    });
  });

  document.getElementById("btn-voice").addEventListener("click", () => {
    car.light = !car.light;
    document.querySelector('.ctrl[data-key="light"]').classList.toggle("on", car.light);
    document.getElementById("btn-voice").classList.add("flash");
    setTimeout(() => document.getElementById("btn-voice").classList.remove("flash"), 800);
    log("[语音] 识别: 干杯出来开灯");
  });

  ["throttle", "brake"].forEach(id => {
    const el = document.getElementById(id);
    const apply = clientY => {
      const r = el.getBoundingClientRect();
      const v = Math.max(0, Math.min(100, Math.round((r.bottom - clientY) / r.height * 100)));
      car[id] = v;
      el.style.setProperty("--pedal", v + "%");
      el.querySelector(".p-val").textContent = v + "%";
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

  // 方向盘：水平拖动转向
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
    car.steer = Math.max(-1, Math.min(1, car.steer + dx * 0.035));
    wheelEl.style.transform = `rotate(${(car.steer * 90).toFixed(0)}deg)`;
    document.getElementById("steer-val").textContent = `${Math.round(car.steer * 90)}°`;
    car.turn = car.steer < -0.25 ? "L" : car.steer > 0.25 ? "R" : "off";
  };
  window.addEventListener("mousemove", steerMove);
  window.addEventListener("touchmove", e => { if (steerDrag) { e.preventDefault(); steerMove(e.touches[0]); } }, { passive: false });

  document.body.addEventListener("click", () => initAudio());
  document.body.addEventListener("touchstart", () => initAudio());
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
  const r = 6.8;
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
  document.getElementById("speed-num").textContent = Math.round(car.speed);
}, 100);

// ================= 启动 =================
initScene();
buildCar();
bindControls();
bindOrbit();
initCamera();
initTalk();
updateOrbit();
animate();
log("干杯一号 数字孪生已启动");
log("点画面启用声音 · 拖拽旋转视角 · 拖动方向盘转向");
