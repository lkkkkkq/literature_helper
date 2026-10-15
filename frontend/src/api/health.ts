import type { HealthStatus } from '../../../desktop/src/shared/contracts'

export async function getHealth(): Promise<HealthStatus> {
  if (!window.litextract) throw new Error('请通过桌面应用打开工作台（npm run dev）。')
  return window.litextract.health()
}
