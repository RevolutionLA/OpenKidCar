/* ============================================================
 * 干杯一号 · 数字孪生驾驶舱
 * Three.js 3D 车模 + 灯光联动 + 真实摄像头 + 录音对讲 + 引擎声
 * ============================================================ */

// ================= 仿真状态 =================
const car = {
  throttle: 0, brake: 0, gear: 2,
  light: false, mute: false, strip: false, horn: false, ebrk: false,
  speed: 0,
};
const GEAR_MAX = { 1: 10, 2: 15, 3: 20, 4: 25 };

// ================= Three.js 场景 =================
let scene, camera, renderer, carGroup;
const wheels = [];
let headlightMat, brakeMat, stripMat, headLamp;
let carZ = 0;

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

  // 车前灯 SpotLight（默认关闭）
  headLamp = new THREE.SpotLight(0xffffff, 0, 25, Math.PI / 5, 0.4);
  headLamp.position.set(0, 0.5, 1.3);
  headLamp.target.position.set(0, 0, 6);
  scene.add(headLamp);
  scene.add(headLamp.target);

  // 车后方氛围点光（刹车/灯带氛围）
  window.addEventListener("resize", () => {
    camera.aspect = innerWidth / innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(innerWidth, innerHeight);
  });
}

function buildCar() {
  carGroup = new THREE.Group();
  const bodyMat = new THREE.MeshStandardMaterial({ color: 0x1e4fd8, metalness: 0.55, roughness: 0.35 });
  const darkMat = new THREE.MeshStandardMaterial({ color: 0x1a2230, metalness: 0.4, roughness: 0.7 });

  // 底盘 + 车身
  const chassis = new THREE.Mesh(new THREE.BoxGeometry(1.7, 0.2, 0.95), bodyMat);
  chassis.position.y = 0.3;
  const main = new THREE.Mesh(new THREE.BoxGeometry(1.5, 0.38, 0.9), bodyMat);
  main.position.set(0, 0.52, 0);
  const nose = new THREE.Mesh(new THREE.BoxGeometry(0.6, 0.28, 0.68), bodyMat);
  nose.position.set(0.95, 0.52, 0);

  // 座位 + 靠背
  const seat = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.45, 0.48), darkMat);
  seat.position.set(-0.2, 0.66, 0.06);
  const back = new THREE.Mesh(new THREE.BoxGeometry(0.55, 0.65, 0.12), darkMat);
  back.position.set(-0.35, 0.8, -0.26);

  // 方向盘
  const steer = new THREE.Mesh(new THREE.TorusGeometry(0.15, 0.04, 8, 18), darkMat);
  steer.position.set(0.5, 0.72, 0.16);
  steer.rotation.x = Math.PI / 2.6;

  // 四个车轮
  const wheelMat = new THREE.MeshStandardMaterial({ color: 0x0d0f14, roughness: 0.9 });
  [[-0.65, 0.5], [0.65, 0.5], [-0.65, -0.5], [0.65, -0.5]].forEach(([x, z]) => {
    const w = new THREE.Mesh(new THREE.CylinderGeometry(0.3, 0.3, 0.22, 20), wheelMat);
    w.position.set(x, 0.3, z);
    w.rotation.z = Math.PI / 2;
    wheels.push(w);
  });

  // 前灯（emissive，开灯亮）
  headlightMat = new THREE.MeshStandardMaterial({ color: 0xffffff, emissive: 0xffffff, emissiveIntensity: 0 });
  [[0.55, 0.47, 0.46], [-0.55, 0.47, 0.46]].forEach(([x, y, z]) => {
    const l = new THREE.Mesh(new THREE.BoxGeometry(0.3, 0.17, 0.06), headlightMat);
    l.position.set(x, y, z);
    carGroup.add(l);
  });

  // 刹车灯（红色，刹车亮）
  brakeMat = new THREE.MeshStandardMaterial({ color: 0xff2020, emissive: 0xff2020, emissiveIntensity: 0 });
  const brakeBar = new THREE.Mesh(new THREE.BoxGeometry(1.15, 0.13, 0.05), brakeMat);
  brakeBar.position.set(0, 0.58, -0.46);
  carGroup.add(brakeBar);

  // 灯带（车身两侧，彩色流动）
  stripMat = new THREE.MeshStandardMaterial({ color: 0x00ffff, emissive: 0x00ffff, emissiveIntensity: 0 });
  [[0.78, 0], [-0.78, 0]].forEach(([x, z]) => {
    const s = new THREE.Mesh(new THREE.BoxGeometry(0.045, 0.05, 0.95), stripMat);
    s.position.set(x, 0.45, z);
    carGroup.add(s);
  });

  carGroup.add(chassis, main, nose, seat, back, steer, ...wheels);
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
}

// ================= 车运动 =================
function updateCar(dt) {
  const max = GEAR_MAX[car.gear];
  if (car.ebrk) {
    car.speed *= 0.9;
  } else if (car.brake > 10) {
    car.speed *= Math.max(0, 1 - 2.5 * dt);
  } else {
    const target = car.throttle / 100 * max;
    car.speed += (target - car.speed) * Math.min(1, dt * 2.5);
  }
  car.speed = Math.max(0, Math.min(max, car.speed));
  carZ += car.speed * dt * 0.7;
  carGroup.position.z = (carZ % 24) - 0; // 循环行驶
  wheels.forEach(w => (w.rotation.x += car.speed * dt * 3.2));
  // 行驶震动
  carGroup.rotation.z = Math.sin(Date.now() / 60) * car.speed * 0.0012;
  carGroup.rotation.x = Math.sin(Date.now() / 90) * car.speed * 0.0006;
  updateVisuals();
}

// ================= 引擎声（Web Audio） =================
let actx, engGain, engFilter, osc1, osc2, noiseGain;
function initAudio() {
  if (actx) { actx.resume(); return; }
  try {
    actx = new (window.AudioContext || window.webkitAudioContext)();
    engGain = actx.createGain();
    engGain.gain.value = 0;
    engGain.connect(actx.destination);
    engFilter = actx.createBiquadFilter();
    engFilter.type = "lowpass";
    engFilter.frequency.value = 400;
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

    // 排气噪声
    const buf = actx.createBuffer(1, actx.sampleRate * 2, actx.sampleRate);
    const d = buf.getChannelData(0);
    for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
    const noise = actx.createBufferSource();
    noise.buffer = buf;
    noise.loop = true;
    const nf = actx.createBiquadFilter();
    nf.type = "bandpass";
    nf.frequency.value = 130;
    nf.Q.value = 0.8;
    noiseGain = actx.createGain();
    noiseGain.gain.value = 0;
    noise.connect(nf);
    nf.connect(noiseGain);
    noiseGain.connect(engGain);
    noise.start();
  } catch (e) {
    console.log("音频初始化失败:", e);
  }
}

function updateEngine() {
  if (!actx) return;
  const t = car.throttle / 100;
  const rpm = 40 + t * 220;
  osc1.frequency.value = rpm;
  osc2.frequency.value = rpm * 0.5;
  engFilter.frequency.value = 300 + t * 1400;
  const vol = car.mute || car.ebrk ? 0 : 0.02 + t * 0.17;
  engGain.gain.value += (vol - engGain.gain.value) * 0.08;
  noiseGain.gain.value = t * 0.06;
}

// ================= HUD 交互 =================
function log(msg) {
  const el = document.getElementById("log");
  el.innerHTML = msg + "<br>" + el.innerHTML;
  if (el.children.length > 6) el.removeChild(el.lastChild);
}

function bindControls() {
  // 中控按钮
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

  // 档位
  document.querySelectorAll(".gear").forEach(b => {
    b.addEventListener("click", () => {
      car.gear = +b.dataset.g;
      document.querySelectorAll(".gear").forEach(x => x.classList.toggle("active", x === b));
      document.getElementById("gear-label").textContent = `档位 ${car.gear}`;
      log(`换档 -> ${car.gear} 档`);
    });
  });

  // 语音按钮（模拟一条语音指令）
  document.getElementById("btn-voice").addEventListener("click", () => {
    car.light = !car.light;
    document.querySelector('.ctrl[data-key="light"]').classList.toggle("on", car.light);
    document.getElementById("btn-voice").classList.add("flash");
    setTimeout(() => document.getElementById("btn-voice").classList.remove("flash"), 800);
    log(`[语音] 识别: 干杯出来开灯`);
  });

  // 踏板
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

  // 点击画面启用声音
  document.body.addEventListener("click", () => initAudio(), { once: false });
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

// ================= 视角轨道（鼠标拖拽旋转） =================
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
  const volt = (24.6 - car.throttle * 0.008).toFixed(1);
  document.getElementById("d-volt").textContent = volt;
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
log("点画面启用声音 · 拖拽旋转视角");
