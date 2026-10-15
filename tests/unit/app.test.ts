import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from '../../frontend/src/app/HealthPanel.vue'

afterEach(() => {
  delete window.litextract
})
describe('desktop health screen', () => {
  it('renders authenticated backend readiness', async () => {
    window.litextract = {
      chooseFolder: vi.fn(),
      request: vi.fn(),
      health: vi.fn().mockResolvedValue({
        status: 'ok',
        service: 'litextract-v2',
        version: '0.1.0',
        database: 'wal',
        migration: '0001_baseline',
      }),
    }
    const view = mount(App)
    await flushPromises()
    expect(view.get('[data-testid="connection-state"]').text()).toBe('工作台已就绪')
    expect(view.text()).toContain('SQLite · WAL')
    view.unmount()
  })
  it('shows a useful error when opened outside Electron', async () => {
    const view = mount(App)
    await flushPromises()
    expect(view.get('[role="alert"]').text()).toContain('桌面应用')
    view.unmount()
  })
  it('can recover after a failed health check', async () => {
    const check = vi.fn().mockRejectedValueOnce(new Error('连接中断')).mockResolvedValue({
      status: 'ok',
      database: 'wal',
      version: '0.1.0',
      migration: '0001_baseline',
    })
    window.litextract = { health: check, chooseFolder: vi.fn(), request: vi.fn() }
    const view = mount(App)
    await flushPromises()
    expect(view.get('[role="alert"]').text()).toBe('连接中断')
    await view.get('button').trigger('click')
    await flushPromises()
    expect(view.find('[role="alert"]').exists()).toBe(false)
    expect(check).toHaveBeenCalledTimes(2)
    view.unmount()
  })
})
