const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("jarvisAPI", {
  setIgnore: (ignore) => ipcRenderer.send("set-ignore", ignore),
});
