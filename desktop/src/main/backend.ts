import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process'
import { randomBytes } from 'node:crypto'
import { createInterface } from 'node:readline'
import { join } from 'node:path'
import type { HealthStatus } from '../shared/contracts'
import { app } from 'electron'

export class BackendProcess {
  private child?: ChildProcessWithoutNullStreams
  private port?: number
  private token = randomBytes(32).toString('hex')
  private stopping = false
  private exited = false

  constructor(
    private readonly root: string,
    private readonly dataDir: string,
    private readonly onCrash: () => void,
  ) {}

  async start(): Promise<void> {
    const workingRoot = app.isPackaged ? join(process.resourcesPath, 'engine') : this.root
    const python = app.isPackaged
      ? join(workingRoot, 'python.exe')
      : (process.env.LITEXTRACT_PYTHON ??
        join(
          this.root,
          '.venv',
          process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python',
        ))
    const child = spawn(python, ['-m', 'backend.runner'], {
      cwd: workingRoot,
      windowsHide: true,
      env: {
        ...process.env,
        PYTHONUNBUFFERED: '1',
        PYTHONUTF8: '1',
        ...(app.isPackaged
          ? {
              LITEXTRACT_MODEL_DIR: join(process.resourcesPath, 'models'),
              LITEXTRACT_MINERU_PYTHON: join(process.resourcesPath, 'engine-next', 'python.exe'),
              LITEXTRACT_PANDOC: join(
                process.resourcesPath,
                'engine-next',
                'Lib',
                'site-packages',
                'pypandoc',
                'files',
                'pandoc.exe',
              ),
              LITEXTRACT_PARSER_MODELS: join(process.resourcesPath, 'parser-models'),
              MINERU_HOME: join(this.dataDir, 'parser-runtime'),
            }
          : {}),
        LITEXTRACT_API_TOKEN: this.token,
        LITEXTRACT_DATA_DIR: this.dataDir,
      },
      stdio: ['pipe', 'pipe', 'pipe'],
    })
    this.child = child
    child.stdin.on('error', () => {
      /* Exit can race with the shutdown write. */
    })
    child.stderr.on('data', (chunk: Buffer) => process.stderr.write(chunk))
    child.once('exit', () => {
      this.exited = true
      if (this.port && !this.stopping) this.onCrash()
    })
    await new Promise<void>((resolve, reject) => {
      const lines = createInterface({ input: child.stdout })
      const timer = setTimeout(() => done(new Error('后端启动超时（30 秒）。')), 30000)
      const onError = () => done(new Error('无法启动 Python，请先运行安装脚本。'))
      const onExit = () => done(new Error('后端在就绪前退出，请检查终端日志。'))
      const done = (error?: Error) => {
        clearTimeout(timer)
        lines.close()
        child.off('error', onError)
        child.off('exit', onExit)
        if (error) reject(error)
        else resolve()
      }
      child.once('error', onError)
      child.once('exit', onExit)
      lines.on('line', (line) => {
        try {
          const message = JSON.parse(line)
          if (
            message.event === 'ready' &&
            Number.isInteger(message.port) &&
            message.port > 0 &&
            message.port < 65536
          ) {
            this.port = message.port
            done()
          }
        } catch {
          /* Only structured readiness messages are consumed. */
        }
      })
    })
    await this.health()
  }

  async health(): Promise<HealthStatus> {
    return this.request('/api/health', 'GET') as Promise<HealthStatus>
  }

  async stream(path: string, signal: AbortSignal, callback: (value: unknown) => void) {
    if (!this.port || this.exited) throw new Error('本地后端未连接')
    const response = await fetch(`http://127.0.0.1:${this.port}${path}`, {
      headers: { Authorization: `Bearer ${this.token}` },
      signal,
    })
    if (!response.ok || !response.body) throw new Error('无法订阅任务进度')
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let pending = ''
    try {
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        pending += decoder.decode(value, { stream: true })
        let end: number
        while ((end = pending.indexOf('\n\n')) >= 0) {
          const event = pending.slice(0, end)
          pending = pending.slice(end + 2)
          const data = event.split('\n').find((line) => line.startsWith('data: '))
          if (data) callback(JSON.parse(data.slice(6)))
        }
      }
    } finally {
      reader.releaseLock()
    }
  }

  async request(
    path: string,
    method: string,
    body?: unknown,
    binary = false,
    modelKey?: string,
  ): Promise<unknown> {
    if (!this.port || this.exited) throw new Error('本地后端未连接')
    const response = await fetch(`http://127.0.0.1:${this.port}${path}`, {
      method,
      headers: {
        Authorization: `Bearer ${this.token}`,
        'Content-Type': 'application/json',
        ...(modelKey ? { 'X-Model-Key': modelKey } : {}),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(
        path.includes('/scan')
          ? 600000
          : path.includes('/answers') ||
              path.includes('/plans') ||
              path.endsWith('/route') ||
              path.endsWith('/test')
            ? 240000
            : 30000,
      ),
    })
    if (!response.ok) {
      const error = await response.json().catch(() => ({}))
      throw new Error(
        typeof error.detail === 'string'
          ? error.detail
          : `请求失败 (${response.status})，请检查输入。`,
      )
    }
    if (binary) return new Uint8Array(await response.arrayBuffer())
    return response.status === 204 ? null : response.json()
  }

  async stop(): Promise<void> {
    this.stopping = true
    const child = this.child
    if (!child || this.exited || !child.pid) return
    await new Promise<void>((resolve) => {
      const timer = setTimeout(() => child.kill(), 5000)
      child.once('exit', () => {
        clearTimeout(timer)
        resolve()
      })
      child.stdin.end('shutdown\n')
    })
  }
}
