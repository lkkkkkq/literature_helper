import type { DesktopBridge } from '../../desktop/src/shared/contracts'
declare global {
  interface Window {
    litextract?: DesktopBridge
  }
}
