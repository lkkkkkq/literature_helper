import { describe, expect, it } from 'vitest'
import { workspaceRoute } from '../../desktop/src/main/workspace-api'
import type { WorkspaceRequest } from '../../desktop/src/shared/contracts'

const projectId = '11111111-1111-1111-1111-111111111111'
const sessionId = '22222222-2222-2222-2222-222222222222'
describe('restricted workspace bridge', () => {
  it('binds session requests to their project scope', () => {
    expect(workspaceRoute({ action: 'addMessage', projectId, sessionId, content: 'note' })).toEqual(
      {
        path: `/api/projects/${projectId}/sessions/${sessionId}/messages`,
        method: 'POST',
        body: { content: 'note' },
      },
    )
  })
  it('rejects path injection and unknown actions', () => {
    expect(() => workspaceRoute({ action: 'documents', projectId: '../../secrets' })).toThrow()
    expect(() =>
      workspaceRoute({ action: 'fetch', projectId } as unknown as WorkspaceRequest),
    ).toThrow()
    expect(() => workspaceRoute(null as unknown as WorkspaceRequest)).toThrow()
  })
})
