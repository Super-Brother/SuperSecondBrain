const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("secondbrain", {
  getBackendBaseUrl: () => ipcRenderer.invoke("backend:getBaseUrl"),
  selectVaultDirectory: () => ipcRenderer.invoke("dialog:selectVaultDirectory"),
  openExternal: (target: string) => ipcRenderer.invoke("shell:openExternal", target),
  openPath: (target: string) => ipcRenderer.invoke("shell:openPath", target)
});
