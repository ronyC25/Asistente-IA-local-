// Avatar Live2D de Jarvis: Pixi + pixi-live2d-display + wLipSync + WebSocket + microfono.
// Multi-modelo: la lista y la escala se leen de /avatar/config (backend).
import { createWLipSyncNode } from "./vendor/wlipsync-single.js";

const CONFIG = {
  wsUrl: `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`,
  lipsyncProfile: "public/lipsync/profile.json",
  height: 350,
  defaultModel: "Haru",
  models: [],
};

// Espacio reservado abajo para la barra de chat (px).
const RESERVE_BOTTOM = 132;

// Fallback si /avatar/config no esta disponible (p. ej. backend antiguo).
const FALLBACK_MODELS = [
  { name: "Haru", path: "public/models/Haru/haru_greeter_t03.model3.json" },
  { name: "Wanko", path: "public/models/Wanko/Wanko.model3.json" },
];

// Mapa emocion -> expresion por modelo (solo los que tienen expresiones).
const EMOTION_MAPS = {
  Haru: {
    joy: "f01",
    happy: "f01",
    excited: "f02",
    sad: "f03",
    angry: "f04",
    surprised: "f05",
    relaxed: "f06",
    shy: "f07",
    confused: "f07",
    smug: "f02",
    neutral: null,
    thinking: null,
  },
  Wanko: {}, // sin expresiones (solo idle + parpadeo)
};

const $ = (id) => document.getElementById(id);
const stateEl = { dot: $("dot"), text: $("statetext") };
const subtitle = $("subtitle");
const confirmBox = $("confirm");
const input = $("input");
const sendBtn = $("send");
const micBtn = $("mic");
const startBox = $("start");
const startBtn = $("startBtn");
const modelSel = $("modelSel");
const grip = $("grip");
const bar = $("bar");
const expandBtn = $("expand");

let app, model, currentModelName = null;
let mouthIds = ["ParamMouthOpenY"];
let ws, wsReady = false;
let wsFails = 0;
let audioCtx, lipsyncNode, silentGain;
let micStream, micSource, micProc;
let micEnabled = true;
let state = "idle";
let started = false;
const audioSources = new Set();

function fail(step, err) {
  const name = err && err.name ? err.name + ": " : "";
  const msg = err && err.message ? err.message : String(err);
  console.error(`[avatar] fallo en ${step}:`, err);
  setStatus(`Error en ${step}: ${name}${msg}`);
}

// ---------------------------------------------------------------- Mensaje (expandir/ocultar)
function collapseMessage() {
  bar.classList.remove("expanded");
  expandBtn.textContent = "Ver todo";
}

function updateExpandButton() {
  const overflow = subtitle.scrollHeight > subtitle.clientHeight + 1;
  const expanded = bar.classList.contains("expanded");
  expandBtn.style.display = overflow || expanded ? "inline-block" : "none";
}

function setSubtitle(html) {
  subtitle.innerHTML = html;
  collapseMessage();
  updateExpandButton();
}

function setStatus(text) {
  subtitle.textContent = text;
  collapseMessage();
  updateExpandButton();
}

// ---------------------------------------------------------------- Config
async function loadConfig() {
  let cfg = null;
  try {
    const r = await fetch("/avatar/config", { cache: "no-store" });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    cfg = await r.json();
  } catch (e) {
    console.warn("[avatar] /avatar/config no disponible; uso la lista por defecto", e);
  }
  CONFIG.height = cfg && typeof cfg.height === "number" ? cfg.height : 350;
  CONFIG.models = cfg && cfg.models && cfg.models.length ? cfg.models : FALLBACK_MODELS;
  CONFIG.defaultModel = (cfg && cfg.default) || CONFIG.models[0].name;
  if (cfg && cfg.lipsync_profile) CONFIG.lipsyncProfile = cfg.lipsync_profile;
  modelSel.innerHTML = "";
  for (const m of CONFIG.models) {
    const opt = document.createElement("option");
    opt.value = m.name;
    opt.textContent = m.name;
    modelSel.appendChild(opt);
  }
}

// ---------------------------------------------------------------- Pixi + Live2D
async function initPixi() {
  window.PIXI = PIXI;
  if (!PIXI.live2d) throw new Error("pixi-live2d-display no cargado (revisa vendor/)");
  app = new PIXI.Application({
    view: $("canvas"),
    backgroundAlpha: 0,
    resizeTo: window,
    antialias: true,
  });
  window.addEventListener("resize", fitModel);
  app.ticker.add(applyMouth);
}

async function detectMouthIds(modelPath) {
  try {
    const data = await fetch(modelPath).then((r) => r.json());
    const lip = (data.Groups || []).find(
      (g) => (g.Name || "").toLowerCase() === "lipsync"
    );
    if (lip && Array.isArray(lip.Ids) && lip.Ids.length) return lip.Ids;
  } catch (e) {
    /* usa el fallback */
  }
  return ["ParamMouthOpenY"];
}

async function loadModel(name, path) {
  if (model) {
    app.stage.removeChild(model);
    model.destroy();
    model = null;
  }
  model = await PIXI.live2d.Live2DModel.from(path);
  app.stage.addChild(model);
  mouthIds = await detectMouthIds(path);
  currentModelName = name;
  fitModel();
  const im = model.internalModel;
  if (im && typeof im.on === "function") im.on("beforeModelUpdate", applyMouth);
  if (modelSel.value !== name) modelSel.value = name;
}

async function applyModel(name) {
  const m = CONFIG.models.find((x) => x.name === name) || CONFIG.models[0];
  if (!m) return;
  try {
    await loadModel(m.name, m.path);
    localStorage.setItem("jarvis.model", m.name);
  } catch (e) {
    fail("modelo", e);
  }
}

function fitModel() {
  if (!model) return;
  const w = window.innerWidth;
  const h = window.innerHeight;
  const availH = h - RESERVE_BOTTOM - 16;
  const targetH = Math.min(CONFIG.height, availH);
  const s = Math.min(targetH / model.height, (w * 0.94) / model.width);
  model.scale.set(s);
  model.anchor.set(0.5, 1);
  model.x = w / 2;
  model.y = h - RESERVE_BOTTOM;
}

// ---------------------------------------------------------------- Lip-sync
async function initLipsync() {
  if (lipsyncNode) return;
  if (!audioCtx) audioCtx = new AudioContext();
  const profile = await fetch(CONFIG.lipsyncProfile).then((r) => r.json());
  lipsyncNode = await createWLipSyncNode(audioCtx, profile);
  silentGain = audioCtx.createGain();
  silentGain.gain.value = 0;
  lipsyncNode.connect(silentGain);
  silentGain.connect(audioCtx.destination);
}

function setParam(core, id, v, lo = 0, hi = 1) {
  try {
    core.setParameterValueById(id, Math.max(lo, Math.min(hi, v)), 1);
  } catch (e) {
    /* parametro inexistente */
  }
}

function applyMouth() {
  if (!model || !lipsyncNode || !model.internalModel) return;
  const core = model.internalModel.coreModel;
  const vol = Math.min(1, (lipsyncNode.volume || 0) * 1.8);
  for (const id of mouthIds) setParam(core, id, vol);
  const w = lipsyncNode.weights || {};
  const abierta = (w.I || 0) + (w.E || 0);
  const redonda = (w.O || 0) + (w.U || 0);
  setParam(core, "ParamMouthForm", Math.max(-1, Math.min(1, abierta - redonda)), -1, 1);
}

function setExpression(emotion) {
  if (!model) return;
  const name = (EMOTION_MAPS[currentModelName] || {})[emotion];
  if (!name) return;
  try {
    model.expression(name);
  } catch (e) {
    /* expresion inexistente */
  }
}

function onClickModel() {
  if (!model) return;
  const names = [...new Set(Object.values(EMOTION_MAPS[currentModelName] || {}).filter(Boolean))];
  try {
    if (names.length) {
      model.expression(names[Math.floor(Math.random() * names.length)]);
    } else {
      model.motion("TapBody");
    }
  } catch (e) {
    /* sin expresiones ni motions */
  }
}

async function playWav(arrayBuffer) {
  try {
    if (audioCtx.state === "suspended") await audioCtx.resume();
    const buf = await audioCtx.decodeAudioData(arrayBuffer.slice(0));
    const src = audioCtx.createBufferSource();
    src.buffer = buf;
    src.connect(audioCtx.destination);
    if (lipsyncNode) src.connect(lipsyncNode);
    audioSources.add(src);
    src.onended = () => audioSources.delete(src);
    src.start();
  } catch (e) {
    console.error("playWav", e);
  }
}

function stopSpeaking() {
  for (const src of [...audioSources]) {
    try {
      src.stop();
    } catch (_) {
      /* ya termino */
    }
    audioSources.delete(src);
  }
}

// ---------------------------------------------------------------- Microfono
async function startMic() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    throw new Error("getUserMedia no disponible (contexto no seguro)");
  }
  const intentos = [
    {
      // Primero con cancelacion de eco: evita que el micro capte la voz del avatar.
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
        channelCount: 1,
      },
    },
    { audio: true },
  ];
  let lastErr = null;
  for (const c of intentos) {
    try {
      micStream = await navigator.mediaDevices.getUserMedia(c);
      break;
    } catch (e) {
      lastErr = e;
    }
  }
  if (!micStream) throw lastErr || new Error("no se pudo acceder al microfono");

  if (audioCtx.state === "suspended") await audioCtx.resume();
  micSource = audioCtx.createMediaStreamSource(micStream);
  micProc = audioCtx.createScriptProcessor(4096, 1, 1);
  micSource.connect(micProc);
  const mute = audioCtx.createGain();
  mute.gain.value = 0;
  micProc.connect(mute);
  mute.connect(audioCtx.destination);
  micProc.onaudioprocess = (e) => {
    if (!micEnabled || !wsReady) return;
    // Barge-in: durante "speaking" el micro sigue activo para detectar la wake
    // word; el servidor es quien corta el audio. Solo se pausa al pensar.
    if (state === "thinking") return;
    const input = e.inputBuffer.getChannelData(0);
    ws.send(floatToInt16(downsample(input, audioCtx.sampleRate, 16000)));
  };
  micBtn.classList.add("on");
  micBtn.textContent = "Mic ON";
}

function stopMic() {
  if (micProc) micProc.onaudioprocess = null;
  if (micStream) micStream.getTracks().forEach((t) => t.stop());
  micStream = micSource = micProc = null;
  micBtn.classList.remove("on");
  micBtn.textContent = "Mic OFF";
}

function downsample(buffer, inRate, outRate) {
  if (outRate === inRate) return buffer;
  const ratio = inRate / outRate;
  const outLen = Math.round(buffer.length / ratio);
  const out = new Float32Array(outLen);
  for (let i = 0; i < outLen; i++) out[i] = buffer[Math.round(i * ratio)] || 0;
  return out;
}

function floatToInt16(f32) {
  const buf = new Int16Array(f32.length);
  for (let i = 0; i < f32.length; i++) {
    const s = Math.max(-1, Math.min(1, f32[i]));
    buf[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return buf.buffer;
}

// ---------------------------------------------------------------- WebSocket
function connect() {
  ws = new WebSocket(CONFIG.wsUrl);
  ws.binaryType = "arraybuffer";
  ws.onopen = () => {
    wsReady = true;
    wsFails = 0;
    if (!started) setStatus('Conectado. Di "hey jarvis" o escribe abajo.');
  };
  ws.onclose = () => {
    wsReady = false;
    wsFails++;
    if (wsFails >= 2 && !started) {
      setStatus("Sin conexion con el servidor. Arranca el backend (start-web.ps1 o --web).");
    }
    setTimeout(connect, 2500);
  };
  ws.onerror = () => { wsReady = false; };
  ws.onmessage = (ev) => {
    if (typeof ev.data !== "string") { playWav(ev.data); return; }
    let msg;
    try { msg = JSON.parse(ev.data); } catch { return; }
    handleMessage(msg);
  };
}

function handleMessage(msg) {
  switch (msg.type) {
    case "ready":
      setStatus(`Listo. Di "hey jarvis" o escribe abajo.`);
      break;
    case "state":
      setState(msg.value);
      break;
    case "you":
      setSubtitle(`<span class="who">Tu:</span> ${escapeHtml(msg.text)}`);
      break;
    case "reply":
      setSubtitle(`<span class="who">Jarvis:</span> ${escapeHtml(msg.text)}`);
      break;
    case "expression":
      setExpression(msg.value);
      break;
    case "stop_speaking":
      stopSpeaking();
      break;
    case "pending":
      confirmBox.style.display = msg.active ? "flex" : "none";
      break;
    case "error":
      setStatus("Error: " + msg.message);
      break;
  }
}

function setState(value) {
  state = value;
  stateEl.dot.className = value;
  stateEl.text.textContent = value;
}

function escapeHtml(s) {
  return (s || "").replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

function sendText(text) {
  if (!text.trim() || !wsReady) return;
  stopSpeaking();
  ws.send(JSON.stringify({ type: "text", text }));
  input.value = "";
}

// ---------------------------------------------------------------- Temporizador
const timerBtn = $("timerBtn");
let timersActivos = [];

function fmtMMSS(seg) {
  seg = Math.max(0, Math.floor(seg));
  const m = Math.floor(seg / 60);
  const s = seg % 60;
  return String(m).padStart(2, "0") + ":" + String(s).padStart(2, "0");
}

function updateTimerBtn() {
  if (!timersActivos.length) {
    timerBtn.className = "ghost idle";
    timerBtn.textContent = "🕐";
    return;
  }
  const now = Date.now();
  let min = Infinity;
  let nearest = null;
  for (const t of timersActivos) {
    const seg =
      t.estado === "pausado"
        ? Number(t.restante_seg || 0)
        : t.fin
        ? (Date.parse(t.fin) - now) / 1000
        : 0;
    if (seg < min) {
      min = seg;
      nearest = t;
    }
  }
  let cls = "work";
  if (nearest.estado === "pausado") cls = "paused";
  else if (nearest.tipo === "pomodoro")
    cls = nearest.fase === "trabajo" ? "work" : "break";
  timerBtn.className = "ghost " + cls;
  timerBtn.textContent = "🕐 " + fmtMMSS(min);
}

async function pollTimers() {
  try {
    const r = await fetch("/temporizadores", { cache: "no-store" });
    const data = await r.json();
    timersActivos = data.temporizadores || [];
    updateTimerBtn();
  } catch (e) {
    /* sin conexion */
  }
}

setInterval(pollTimers, 3000);
setInterval(updateTimerBtn, 1000);
pollTimers();
timerBtn.addEventListener("click", () => {
  const api = window.jarvisAPI;
  if (api && api.openTimer) api.openTimer();
  else window.open("/avatar/timer.html", "_blank", "width=420,height=640");
});

// ---------------------------------------------------------------- UI
sendBtn.addEventListener("click", () => sendText(input.value));
input.addEventListener("keydown", (e) => { if (e.key === "Enter") sendText(input.value); });
confirmBox.querySelectorAll("button").forEach((b) =>
  b.addEventListener("click", () => sendText(b.dataset.answer)));
micBtn.addEventListener("click", () => {
  micEnabled = !micEnabled;
  micBtn.classList.toggle("on", micEnabled);
  micBtn.textContent = micEnabled ? "Mic ON" : "Mic OFF";
});
modelSel.addEventListener("change", () => applyModel(modelSel.value));
expandBtn.addEventListener("click", () => {
  const expanded = bar.classList.toggle("expanded");
  expandBtn.textContent = expanded ? "Ocultar" : "Ver todo";
  if (expanded) subtitle.scrollTop = 0;
  updateExpandButton();
});

window.addEventListener("pointermove", (e) => {
  if (model && typeof model.focus === "function") model.focus(e.clientX, e.clientY);
});
$("canvas").addEventListener("click", onClickModel);

// ---------------------------------------------------------------- Arrastre del overlay
let dragging = false, lastX = 0, lastY = 0;
grip.addEventListener("pointerdown", (e) => {
  const api = window.jarvisAPI;
  if (!api || !api.beginDrag) return;
  dragging = true;
  lastX = e.screenX;
  lastY = e.screenY;
  try { grip.setPointerCapture(e.pointerId); } catch (_) {}
  api.beginDrag();
});
grip.addEventListener("pointermove", (e) => {
  if (!dragging) return;
  const api = window.jarvisAPI;
  const dx = e.screenX - lastX;
  const dy = e.screenY - lastY;
  lastX = e.screenX;
  lastY = e.screenY;
  if (api && api.drag) api.drag(dx, dy);
});
function endDrag() {
  if (!dragging) return;
  dragging = false;
  const api = window.jarvisAPI;
  if (api && api.endDrag) api.endDrag();
}
grip.addEventListener("pointerup", endDrag);
grip.addEventListener("pointercancel", endDrag);

// ---------------------------------------------------------------- Overlay Electron
function overlaySetInteractive(on) {
  const api = window.jarvisAPI;
  if (api) api.setIgnore(!on);
}

function setupOverlayAfterStart() {
  const api = window.jarvisAPI;
  if (!api) return;
  [$("bar"), $("status")].forEach((el) => {
    if (!el) return;
    el.addEventListener("mouseenter", () => api.setIgnore(false));
    el.addEventListener("mouseleave", () => {
      if (!dragging) api.setIgnore(true);
    });
  });
  api.setIgnore(true);
}

// ---------------------------------------------------------------- Arranque
window.addEventListener("error", (e) => fail("global", e.error || e.message));
window.addEventListener("unhandledrejection", (e) => fail("promesa", e.reason));

async function start() {
  if (started) return;
  started = true;
  startBtn.disabled = true;
  try {
    await initLipsync();
  } catch (e) { fail("wLipSync", e); return; }
  try {
    await startMic();
  } catch (e) { fail("microfono", e); }
  startBox.style.display = "none";
  setState("idle");
  setupOverlayAfterStart();
}

async function boot() {
  startBtn.addEventListener("click", start);
  try {
    await loadConfig();
  } catch (e) { fail("config", e); }
  try {
    await initPixi();
  } catch (e) { fail("pixi", e); return; }
  const saved = localStorage.getItem("jarvis.model");
  const initial = CONFIG.models.find((m) => m.name === saved)
    ? saved
    : CONFIG.defaultModel;
  try {
    await applyModel(initial);
  } catch (e) { fail("modelo", e); return; }
  try {
    connect();
  } catch (e) { fail("websocket", e); }
  overlaySetInteractive(true); // permitir pulsar "Iniciar" en Electron
  startBox.style.display = "flex";
}

boot();
