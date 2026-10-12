// Avatar Live2D de Jarvis: Pixi + pixi-live2d-display + wLipSync + WebSocket + microfono.
// Modelo: Haru (Cubism 4, LipSync = ParamMouthOpenY).
import { createWLipSyncNode } from "./vendor/wlipsync-single.js";

const CONFIG = {
  wsUrl: `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`,
  modelPath: "public/models/Haru/haru_greeter_t03.model3.json",
  lipsyncProfile: "public/lipsync/profile.json",
  // Mapa emocion -> expresion de Haru (f00..f07)
  emotionMap: {
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
  clickExpressions: ["f00", "f01", "f02", "f03", "f04", "f05", "f06", "f07"],
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

let app, model;
let ws, wsReady = false;
let audioCtx, lipsyncNode, silentGain;
let micStream, micSource, micProc;
let micEnabled = true;
let state = "idle";
let started = false;

function fail(step, err) {
  const name = err && err.name ? err.name + ": " : "";
  const msg = err && err.message ? err.message : String(err);
  console.error(`[avatar] fallo en ${step}:`, err);
  subtitle.textContent = `Error en ${step}: ${name}${msg}`;
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
  model = await PIXI.live2d.Live2DModel.from(CONFIG.modelPath);
  app.stage.addChild(model);
  fitModel();
  window.addEventListener("resize", fitModel);
  const im = model.internalModel;
  const hook = () => applyMouth();
  if (im && typeof im.on === "function") im.on("beforeModelUpdate", hook);
  app.ticker.add(hook);
}

function fitModel() {
  if (!model) return;
  const w = window.innerWidth;
  const h = window.innerHeight;
  const scale = Math.min((h * 0.96) / model.height, (w * 0.96) / model.width);
  model.scale.set(scale);
  model.anchor.set(0.5, 1);
  model.x = w / 2;
  model.y = h;
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
  setParam(core, "ParamMouthOpenY", vol);
  const w = lipsyncNode.weights || {};
  const abierta = (w.I || 0) + (w.E || 0);
  const redonda = (w.O || 0) + (w.U || 0);
  setParam(core, "ParamMouthForm", Math.max(-1, Math.min(1, abierta - redonda)), -1, 1);
}

function setExpression(name) {
  if (!model || !name) return;
  try {
    model.expression(name);
  } catch (e) {
    /* expresion inexistente */
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
    src.start();
  } catch (e) {
    console.error("playWav", e);
  }
}

// ---------------------------------------------------------------- Microfono
async function startMic() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    throw new Error("getUserMedia no disponible (contexto no seguro)");
  }
  const intentos = [
    { audio: true },
    {
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
        channelCount: 1,
      },
    },
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
    if (state === "speaking" || state === "thinking") return; // half-duplex
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
  ws.onopen = () => { wsReady = true; };
  ws.onclose = () => { wsReady = false; setTimeout(connect, 2500); };
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
      subtitle.textContent = `Listo. Di "hey jarvis" o escribe abajo.`;
      break;
    case "state":
      setState(msg.value);
      break;
    case "you":
      subtitle.innerHTML = `<span class="who">Tu:</span> ${escapeHtml(msg.text)}`;
      break;
    case "reply":
      subtitle.innerHTML = `<span class="who">Jarvis:</span> ${escapeHtml(msg.text)}`;
      break;
    case "expression":
      setExpression(CONFIG.emotionMap[msg.value] || null);
      break;
    case "pending":
      confirmBox.style.display = msg.active ? "flex" : "none";
      break;
    case "error":
      subtitle.textContent = "Error: " + msg.message;
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
  ws.send(JSON.stringify({ type: "text", text }));
  input.value = "";
}

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

window.addEventListener("pointermove", (e) => {
  if (model && typeof model.focus === "function") model.focus(e.clientX, e.clientY);
});
$("canvas").addEventListener("click", () => {
  const arr = CONFIG.clickExpressions;
  setExpression(arr[Math.floor(Math.random() * arr.length)]);
});

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
    el.addEventListener("mouseleave", () => api.setIgnore(true));
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
    await initPixi();
  } catch (e) { fail("modelo", e); return; }
  try {
    connect();
  } catch (e) { fail("websocket", e); }
  overlaySetInteractive(true); // permitir pulsar "Iniciar" en Electron
  startBox.style.display = "flex";
}

boot();
