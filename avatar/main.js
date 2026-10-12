// Avatar Live2D de Jarvis: Pixi + pixi-live2d-display + wLipSync + WebSocket + microfono.
import { createWLipSyncNode } from "./vendor/wlipsync-single.js";

const CONFIG = {
  wsUrl: `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`,
  modelPath: "public/models/Mao/Mao.model3.json",
  lipsyncProfile: "public/lipsync/profile.json",
  // Mapa emocion -> expresion del modelo (Mao tiene exp_01..exp_08)
  emotionMap: {
    joy: "exp_01",
    happy: "exp_01",
    excited: "exp_02",
    sad: "exp_03",
    angry: "exp_04",
    surprised: "exp_05",
    relaxed: "exp_06",
    shy: "exp_07",
    confused: "exp_08",
    smug: "exp_02",
    neutral: null,
    thinking: null,
  },
};

const $ = (id) => document.getElementById(id);
const stateEl = { dot: $("dot"), text: $("statetext") };
const subtitle = $("subtitle");
const confirmBox = $("confirm");
const input = $("input");
const sendBtn = $("send");
const micBtn = $("mic");

let app, model;
let ws, wsReady = false;
let audioCtx, lipsyncNode, silentGain;
let micStream, micSource, micProc;
let micEnabled = true;
let state = "idle";

// ---------------------------------------------------------------- Pixi + Live2D
async function initPixi() {
  window.PIXI = PIXI;
  if (!PIXI.live2d) throw new Error("pixi-live2d-display no cargado");
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
  audioCtx = new AudioContext();
  const profile = await fetch(CONFIG.lipsyncProfile).then((r) => r.json());
  lipsyncNode = await createWLipSyncNode(audioCtx, profile);
  silentGain = audioCtx.createGain();
  silentGain.gain.value = 0;
  lipsyncNode.connect(silentGain);
  silentGain.connect(audioCtx.destination);
}

function setP(core, id, v) {
  try {
    core.setParameterValueById(id, Math.max(0, Math.min(1, v)), 1);
  } catch (e) {
    /* parametro inexistente */
  }
}

function applyMouth() {
  if (!model || !lipsyncNode || !model.internalModel) return;
  const core = model.internalModel.coreModel;
  const vol = Math.min(1, (lipsyncNode.volume || 0) * 1.6);
  const w = lipsyncNode.weights || {};
  const k = vol * 1.3;
  setP(core, "ParamA", (w.A || 0) * k);
  setP(core, "ParamI", (w.I || 0) * k);
  setP(core, "ParamU", (w.U || 0) * k);
  setP(core, "ParamE", (w.E || 0) * k);
  setP(core, "ParamO", (w.O || 0) * k);
  setP(core, "ParamMouthUp", vol * 0.4);
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
    await audioCtx.resume();
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
  try {
    micStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
        channelCount: 1,
      },
    });
    await audioCtx.resume();
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
      const ds = downsample(input, audioCtx.sampleRate, 16000);
      ws.send(floatToInt16(ds));
    };
    micBtn.classList.add("on");
    micBtn.textContent = "Mic ON";
  } catch (e) {
    setState("idle");
    subtitle.textContent = "No se pudo acceder al microfono: " + e.message;
  }
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
  if (micEnabled) { micBtn.classList.add("on"); micBtn.textContent = "Mic ON"; }
  else { micBtn.classList.remove("on"); micBtn.textContent = "Mic OFF"; }
});

// Interacciones: la mirada sigue al cursor y el clic dispara una expresion.
window.addEventListener("pointermove", (e) => {
  if (model && typeof model.focus === "function") model.focus(e.clientX, e.clientY);
});
$("canvas").addEventListener("click", () => {
  const exps = ["exp_01", "exp_02", "exp_05", "exp_07", "exp_08"];
  setExpression(exps[Math.floor(Math.random() * exps.length)]);
});

// ---------------------------------------------------------------- Arranque
(async function main() {
  try {
    await initPixi();
    await initLipsync();
    connect();
    await startMic();
    setState("idle");
    setupOverlay();
  } catch (e) {
    console.error(e);
    subtitle.textContent = "Error al iniciar: " + e.message;
  }
})();

// ---------------------------------------------------------------- Overlay Electron
function setupOverlay() {
  const api = window.jarvisAPI;
  if (!api) return; // no estamos dentro de Electron
  const interactive = [$("bar"), $("status")];
  interactive.forEach((el) => {
    if (!el) return;
    el.addEventListener("mouseenter", () => api.setIgnore(false));
    el.addEventListener("mouseleave", () => api.setIgnore(true));
  });
  api.setIgnore(true);
}

