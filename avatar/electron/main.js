// Overlay de escritorio: ventana transparente, siempre visible y click-through.
const { app, BrowserWindow, ipcMain, Menu, screen, session } = require("electron");
const fs = require("fs");
const path = require("path");

// Sin cache HTTP: el overlay siempre carga la version actual de index.html/main.js.
app.commandLine.appendSwitch("disable-http-cache");

const URL = process.env.JARVIS_URL || "http://127.0.0.1:8000/avatar/";
const W = 380;
const H = 500;
const MARGIN = 30;
const POS_FILE = path.join(__dirname, "..", "..", "data", "avatar_pos.json");

let win = null;

function loadPos() {
  try {
    const p = JSON.parse(fs.readFileSync(POS_FILE, "utf-8"));
    if (Number.isFinite(p.x) && Number.isFinite(p.y)) return p;
  } catch (e) {
    /* sin posicion guardada */
  }
  return null;
}

function savePos() {
  if (!win) return;
  const [x, y] = win.getPosition();
  try {
    fs.mkdirSync(path.dirname(POS_FILE), { recursive: true });
    fs.writeFileSync(POS_FILE, JSON.stringify({ x, y }), "utf-8");
  } catch (e) {
    console.error("[pos] no se pudo guardar:", e.message);
  }
}

function esquinaInferiorDerecha() {
  const { workArea } = screen.getPrimaryDisplay();
  return {
    x: workArea.x + workArea.width - W - MARGIN,
    y: workArea.y + workArea.height - H - MARGIN,
  };
}

function centrar() {
  const { workArea } = screen.getPrimaryDisplay();
  return {
    x: workArea.x + Math.round((workArea.width - W) / 2),
    y: workArea.y + Math.round((workArea.height - H) / 2),
  };
}

function createWindow() {
  const saved = loadPos();
  const pos = saved || esquinaInferiorDerecha();

  win = new BrowserWindow({
    width: W,
    height: H,
    x: pos.x,
    y: pos.y,
    transparent: true,
    frame: false,
    resizable: false,
    movable: true,
    hasShadow: false,
    skipTaskbar: true,
    fullscreenable: false,
    alwaysOnTop: true,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      backgroundThrottling: false,
      autoplayPolicy: "no-user-gesture-required",
    },
  });

  win.setAlwaysOnTop(true, "screen-saver");
  win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  win.setIgnoreMouseEvents(true, { forward: true }); // click-through por defecto

  // Si falla la carga (backend aun no levantado), reintenta.
  win.webContents.on("did-fail-load", (_e, code, desc, url) => {
    console.error(`[load-fail] ${code} ${desc} ${url}`);
    setTimeout(() => win && win.loadURL(URL), 3000);
  });

  win.loadURL(URL);

  // F12 / Ctrl+Shift+I abren las DevTools (util para depurar el avatar).
  win.webContents.on("before-input-event", (event, input) => {
    const key = (input.key || "").toLowerCase();
    if (
      input.type === "keyDown" &&
      (input.key === "F12" || (input.control && input.shift && key === "i"))
    ) {
      event.preventDefault();
      win.webContents.toggleDevTools();
    }
  });

  const menu = Menu.buildFromTemplate([
    { label: "Mostrar / Ocultar", click: () => (win.isVisible() ? win.hide() : win.show()) },
    { label: "Recargar", click: () => win.reload() },
    { type: "separator" },
    {
      label: "Centrar en pantalla",
      click: () => {
        const p = centrar();
        win.setPosition(p.x, p.y);
        savePos();
      },
    },
    {
      label: "Esquina inferior derecha",
      click: () => {
        const p = esquinaInferiorDerecha();
        win.setPosition(p.x, p.y);
        savePos();
      },
    },
    {
      label: "Restablecer posicion",
      click: () => {
        try { fs.rmSync(POS_FILE); } catch (e) { /* no existia */ }
        const p = esquinaInferiorDerecha();
        win.setPosition(p.x, p.y);
      },
    },
    { type: "separator" },
    { label: "Abrir DevTools", click: () => win.webContents.toggleDevTools() },
    { label: "Salir", click: () => app.quit() },
  ]);
  win.webContents.on("context-menu", () => menu.popup({ window: win }));
}

ipcMain.on("set-ignore", (event, ignore) => {
  const w = BrowserWindow.fromWebContents(event.sender);
  if (w) w.setIgnoreMouseEvents(ignore, { forward: true });
});

ipcMain.on("drag-begin", (event) => {
  const w = BrowserWindow.fromWebContents(event.sender);
  if (w) w.setIgnoreMouseEvents(false);
});

ipcMain.on("drag-move", (event, dx, dy) => {
  const w = BrowserWindow.fromWebContents(event.sender);
  if (!w) return;
  const [x, y] = w.getPosition();
  w.setPosition(x + Math.round(dx), y + Math.round(dy));
});

ipcMain.on("drag-end", (event) => {
  const w = BrowserWindow.fromWebContents(event.sender);
  if (!w) return;
  w.setIgnoreMouseEvents(true, { forward: true });
  savePos();
});

app.whenReady().then(async () => {
  Menu.setApplicationMenu(null);
  try {
    await session.defaultSession.clearCache();
  } catch (e) {
    /* ignore */
  }
  // Permitir microfono (necesario para la voz en el overlay).
  session.defaultSession.setPermissionRequestHandler((_wc, permission, callback) => {
    callback(permission === "media" || permission === "audioCapture");
  });
  session.defaultSession.setPermissionCheckHandler((_wc, permission) => {
    return permission === "media" || permission === "audioCapture";
  });
  createWindow();
});

app.on("window-all-closed", () => app.quit());
