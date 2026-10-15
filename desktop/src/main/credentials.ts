import { safeStorage } from 'electron'
import { mkdir, readFile, rename, rm, writeFile } from 'node:fs/promises'
import { join } from 'node:path'

export class Credentials {
  constructor(private directory: string) {}
  private path(projectId: string) {
    if (!/^[0-9a-f-]{36}$/i.test(projectId)) throw new Error('无效项目')
    return join(this.directory, `${projectId}.bin`)
  }
  async read(projectId: string, baseUrl: string): Promise<string> {
    let encrypted: Buffer
    try {
      encrypted = await readFile(this.path(projectId))
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === 'ENOENT') return ''
      throw new Error('无法读取已保存的模型密钥', { cause: error })
    }
    try {
      const decoded = await safeStorage.decryptStringAsync(encrypted)
      const value = JSON.parse(decoded.result) as { baseUrl: string; key: string }
      return value.baseUrl === baseUrl ? value.key : ''
    } catch {
      throw new Error('系统无法解密此密钥，请重新保存 API Key')
    }
  }
  async save(projectId: string, baseUrl: string, key: string) {
    if (typeof key !== 'string' || !key.trim() || key.length > 4096 || /[\r\n]/.test(key))
      throw new Error('API Key 无效')
    if (!(await safeStorage.isAsyncEncryptionAvailable()))
      throw new Error('系统加密存储不可用，无法保存密钥')
    const encrypted = await safeStorage.encryptStringAsync(
      JSON.stringify({ baseUrl, key: key.trim() }),
    )
    await mkdir(this.directory, { recursive: true })
    const path = this.path(projectId)
    const temporary = `${path}.tmp`
    await writeFile(temporary, encrypted, { mode: 0o600 })
    await rename(temporary, path)
  }
  async remove(projectId: string) {
    await rm(this.path(projectId), { force: true })
  }
}
