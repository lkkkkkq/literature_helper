import { contextBridge, ipcRenderer } from 'electron'
import type { DesktopBridge } from '../shared/contracts'
let subscription = 0

const bridge: DesktopBridge = {
  health: () => ipcRenderer.invoke('system:health'),
  chooseFolder: () => ipcRenderer.invoke('workspace:choose-folder'),
  request: (request) => ipcRenderer.invoke('workspace:request', request),
  watchJob: (projectId, jobId, callback) => {
    const id = String(++subscription)
    const channel = `jobs:progress:${id}`
    const listener = (_event: Electron.IpcRendererEvent, value: Parameters<typeof callback>[0]) =>
      callback(value)
    ipcRenderer.on(channel, listener)
    ipcRenderer.send('jobs:watch', id, projectId, jobId)
    return () => {
      ipcRenderer.removeListener(channel, listener)
      ipcRenderer.send('jobs:unwatch', id)
    }
  },
}
contextBridge.exposeInMainWorld('litextract', bridge)
