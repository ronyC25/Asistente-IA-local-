// Overlay de escritorio: ventana transparente, siempre visible y click-through.
const { app, BrowserWindow, ipcMain, Menu, screen } = require("electron");
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
    },
  });

  win.setAlwaysOnTop(true, "screen-saver");
  win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  win.setIgnoreMouseEvents(true, { forward: true }); // click-through por defecto
  win.loadURL(URL);

  // Reintenta si el backend aun no esta levantado.
  win.webContents.on("did-fail-load", () => {
    setTimeout(() => win && win.loadURL(URL), 3000);
  });

  const menu = Menu.buildFromTemplate([
    { label: "Mostrar / Ocultar", click: () => (win.isVisible() ? win.hide() : win.show()) },
    { label: "Recargar", click: () => win.reload() },
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
  createWindow();
});

app.on("window-all-closed", () => app.quit());
