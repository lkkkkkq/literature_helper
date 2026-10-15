import { afterEach, expect, it, vi } from 'vitest'
import { isProxy, reactive } from 'vue'
import { request } from '../../frontend/src/api/workspace'
import type { WorkspaceRequest } from '../../desktop/src/shared/contracts'

afterEach(() => {
  delete window.litextract
})
it('serializes nested Vue state into plain IPC data', async () => {
  const bridge = vi.fn(async (operation: WorkspaceRequest) => {
    expect(isProxy(operation)).toBe(false)
    if (operation.action === 'confirmScan')
      expect(isProxy(operation.groups[0].asset_paths)).toBe(false)
    return []
  })
  window.litextract = { request: bridge, health: vi.fn(), chooseFolder: vi.fn() }
  const operation = reactive<WorkspaceRequest>({
    action: 'confirmScan',
    projectId: 'p',
    draft_id: 'd',
    groups: [{ title: 'paper', main_path: 'paper.pdf', asset_paths: ['paper.pdf'] }],
  })
  await request(operation)
  expect(bridge).toHaveBeenCalledOnce()
})
