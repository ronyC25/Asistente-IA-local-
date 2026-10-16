const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("jarvisAPI", {
  setIgnore: (ignore) => ipcRenderer.send("set-ignore", ignore),
  beginDrag: () => ipcRenderer.send("drag-begin"),
  drag: (dx, dy) => ipcRenderer.send("drag-move", dx, dy),
  endDrag: () => ipcRenderer.send("drag-end"),
});
