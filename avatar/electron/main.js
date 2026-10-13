// Overlay de escritorio: ventana transparente, siempre visible y click-through.
const { app, BrowserWindow, ipcMain, Menu, screen, session } = require("electron");
const path = require("path");

const URL = process.env.JARVIS_URL || "http://127.0.0.1:8000/avatar/";
const W = 420;
const H = 640;

let win = null;

function createWindow() {
  const { workArea } = screen.getPrimaryDisplay();

  win = new BrowserWindow({
    width: W,
    height: H,
    x: workArea.x + workArea.width - W - 30,
    y: workArea.y + workArea.height - H - 30,
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
    { label: "Abrir DevTools", click: () => win.webContents.toggleDevTools() },
    { type: "separator" },
    { label: "Salir", click: () => app.quit() },
  ]);
  win.webContents.on("context-menu", () => menu.popup({ window: win }));
}

ipcMain.on("set-ignore", (event, ignore) => {
  const w = BrowserWindow.fromWebContents(event.sender);
  if (w) w.setIgnoreMouseEvents(ignore, { forward: true });
});

app.whenReady().then(() => {
  Menu.setApplicationMenu(null);
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
