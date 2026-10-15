import type { WorkspaceRequest } from '../../../desktop/src/shared/contracts'

export async function request<T>(operation: WorkspaceRequest): Promise<T> {
  if (!window.litextract) throw new Error('请通过桌面应用打开工作台（npm run dev）。')
  // Vue reactive arrays are proxies and cannot cross Electron's structured-clone boundary.
  const payload: WorkspaceRequest = JSON.parse(JSON.stringify(operation))
  return window.litextract.request(payload) as Promise<T>
}

export function readableError(error: unknown): string {
  const message = error instanceof Error ? error.message : '操作失败，请重试。'
  return message.replace(/^Error invoking remote method '[^']+': Error: /, '')
}
