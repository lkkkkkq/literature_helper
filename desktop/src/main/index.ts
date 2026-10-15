import { app, BrowserWindow, dialog, ipcMain } from 'electron'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { mkdirSync } from 'node:fs'
import { writeFile } from 'node:fs/promises'
import { BackendProcess } from './backend'
import { workspaceRoute } from './workspace-api'
import { Credentials } from './credentials'
import type { WorkspaceRequest } from '../shared/contracts'

const here = dirname(fileURLToPath(import.meta.url))
let backend: BackendProcess | undefined
let quitting = false
const subscriptions = new Map<string, AbortController>()

// An explicit workspace gets its own browser profile and single-instance lock.
// Automated tests must not target a running user's desktop instance.
if (process.env.LITEXTRACT_DATA_DIR) {
  const profile = resolve(process.env.LITEXTRACT_DATA_DIR, 'desktop')
  mkdirSync(profile, { recursive: true })
  app.setPath('userData', profile)
}

if (!app.requestSingleInstanceLock()) {
  app.quit()
} else {
  app.on('second-instance', () => {
    const window = BrowserWindow.getAllWindows()[0]
    window?.restore()
    window?.focus()
  })
  app.on('window-all-closed', () => app.quit())
  app.on('before-quit', (event) => {
    if (quitting) return
    event.preventDefault()
    quitting = true
    for (const controller of subscriptions.values()) controller.abort()
    subscriptions.clear()
    void (async () => {
      await backend?.stop()
      app.quit()
    })()
  })
  void app.whenReady().then(async () => {
    const root = resolve(here, '../..')
    const dataDir = process.env.LITEXTRACT_DATA_DIR ?? join(app.getPath('userData'), 'LitExtract')
    const credentials = new Credentials(join(dataDir, 'credentials'))
    backend = new BackendProcess(root, dataDir, () => {
      dialog.showErrorBox('LitExtract v2', '本地后端意外退出。请重启应用并查看终端日志。')
      app.quit()
    })
    try {
      await backend.start()
      ipcMain.handle('system:health', (event) => {
        const window = BrowserWindow.fromWebContents(event.sender)
        if (!window || event.senderFrame !== window.webContents.mainFrame)
          throw new Error('Invalid caller')
        return backend!.health()
      })
      ipcMain.handle('workspace:request', async (event, request: WorkspaceRequest) => {
        const window = BrowserWindow.fromWebContents(event.sender)
        if (!window || event.senderFrame !== window.webContents.mainFrame)
          throw new Error('Invalid caller')
        if (request?.action === 'deleteModelKey') {
          await credentials.remove(request.projectId)
          return null
        }
        const route = workspaceRoute(request)
        if (request.action === 'exportResults') {
          const selection = await dialog.showSaveDialog(window, {
            title: '导出提取结果',
            defaultPath: `LitExtract.${request.format}`,
            filters: [{ name: request.format.toUpperCase(), extensions: [request.format] }],
          })
          if (selection.canceled || !selection.filePath) return { cancelled: true }
          const result = (await backend!.request(route.path, route.method)) as { data: string }
          await writeFile(selection.filePath, Buffer.from(result.data, 'base64'))
          return { cancelled: false, path: selection.filePath }
        }
        if (request.action === 'saveModel') {
          const profile = (await backend!.request(route.path, route.method, route.body)) as {
            base_url: string
            model: string
          }
          if (request.apiKey)
            await credentials.save(request.projectId, profile.base_url, request.apiKey)
          return {
            ...profile,
            hasKey: !!(await credentials.read(request.projectId, profile.base_url)),
          }
        }
        if (request.action === 'modelProfile') {
          const profile = (await backend!.request(route.path, route.method)) as {
            base_url: string
            model: string
          } | null
          return profile
            ? {
                ...profile,
                hasKey: !!(await credentials.read(request.projectId, profile.base_url)),
              }
            : null
        }
        let key: string | undefined
        if (
          ['ask', 'testModel', 'route', 'design', 'confirmPlan', 'resumeJob'].includes(
            request.action,
          ) &&
          'projectId' in request
        ) {
          const profile = (await backend!.request(
            `/api/projects/${request.projectId}/model`,
            'GET',
          )) as { base_url: string } | null
          key = profile ? await credentials.read(request.projectId, profile.base_url) : ''
        }
        const result = await backend!.request(
          route.path,
          route.method,
          route.body,
          route.binary,
          key,
        )
        if (request.action === 'deleteProject') await credentials.remove(request.projectId)
        return result
      })
      ipcMain.on('jobs:watch', (event, subscription: string, projectId: string, jobId: string) => {
        const window = BrowserWindow.fromWebContents(event.sender)
        if (
          !window ||
          event.senderFrame !== window.webContents.mainFrame ||
          typeof subscription !== 'string'
        )
          return
        const token = `${event.sender.id}:${subscription}`
        try {
          const route = workspaceRoute({ action: 'job', projectId, jobId })
          const controller = new AbortController()
          subscriptions.get(token)?.abort()
          subscriptions.set(token, controller)
          void backend!
            .stream(`${route.path}/events`, controller.signal, (value) => {
              if (!event.sender.isDestroyed())
                event.sender.send(`jobs:progress:${subscription}`, value)
            })
            .catch(() => {
              if (!controller.signal.aborted && !event.sender.isDestroyed())
                event.sender.send(`jobs:progress:${subscription}`, {
                  error: '进度连接中断，可刷新任务查看状态。',
                })
            })
            .finally(() => {
              if (subscriptions.get(token) === controller) subscriptions.delete(token)
            })
        } catch {
          event.sender.send(`jobs:progress:${subscription}`, { error: '无效的任务订阅' })
        }
      })
      ipcMain.on('jobs:unwatch', (event, subscription: string) => {
        const token = `${event.sender.id}:${subscription}`
        subscriptions.get(token)?.abort()
        subscriptions.delete(token)
      })
      ipcMain.handle('workspace:choose-folder', async (event) => {
        const window = BrowserWindow.fromWebContents(event.sender)
        if (!window || event.senderFrame !== window.webContents.mainFrame)
          throw new Error('Invalid caller')
        const result = await dialog.showOpenDialog(window, {
          title: '选择文献文件夹',
          properties: ['openDirectory'],
        })
        return result.canceled ? null : result.filePaths[0]
      })
      const window = new BrowserWindow({
        width: 1200,
        height: 800,
        minWidth: 900,
        minHeight: 620,
        show: false,
        backgroundColor: '#f6f7f9',
        title: 'LitExtract v2',
        webPreferences: {
          preload: join(here, '../preload/index.cjs'),
          contextIsolation: true,
          nodeIntegration: false,
          sandbox: true,
        },
      })
      window.setMenuBarVisibility(false)
      window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }))
      window.webContents.on('will-navigate', (event) => event.preventDefault())
      window.webContents.session.setPermissionRequestHandler((_contents, _permission, callback) =>
        callback(false),
      )
      window.once('ready-to-show', () => window.show())
      if (process.env.ELECTRON_RENDERER_URL) await window.loadURL(process.env.ELECTRON_RENDERER_URL)
      else await window.loadFile(join(here, '../renderer/index.html'))
    } catch (error) {
      dialog.showErrorBox('启动失败', error instanceof Error ? error.message : '未知启动错误')
      app.quit()
    }
  })
}
