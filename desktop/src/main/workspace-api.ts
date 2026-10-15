import type { WorkspaceRequest } from '../shared/contracts'

function id(value: string): string {
  if (typeof value !== 'string' || !/^[0-9a-f-]{36}$/i.test(value))
    throw new Error('无效的记录标识')
  return value
}

/** Construct only known routes. The renderer cannot supply URLs, tokens or HTTP headers. */
export function workspaceRoute(request: WorkspaceRequest): {
  path: string
  method: string
  body?: unknown
  binary?: boolean
} {
  if (!request || typeof request !== 'object') throw new Error('无效请求')
  if (request.action === 'projects') return { path: '/api/projects', method: 'GET' }
  if (request.action === 'createProject')
    return {
      path: '/api/projects',
      method: 'POST',
      body: { name: request.name, source_path: request.source_path },
    }
  if (!('projectId' in request)) throw new Error('不支持的操作')
  const base = `/api/projects/${id(request.projectId)}`
  switch (request.action) {
    case 'route':
      return { path: `${base}/route`, method: 'POST', body: { text: request.text } }
    case 'plans':
      return { path: `${base}/sessions/${id(request.sessionId)}/plans`, method: 'GET' }
    case 'design':
      return {
        path: `${base}/sessions/${id(request.sessionId)}/plans`,
        method: 'POST',
        body: { goal: request.goal, document_ids: request.document_ids },
      }
    case 'confirmPlan':
      return {
        path: `${base}/sessions/${id(request.sessionId)}/jobs`,
        method: 'POST',
        body: { schema_id: request.schema_id, request_id: request.request_id, plan: request.plan },
      }
    case 'jobs':
      return { path: `${base}/sessions/${id(request.sessionId)}/jobs`, method: 'GET' }
    case 'job':
      return { path: `${base}/jobs/${id(request.jobId)}`, method: 'GET' }
    case 'cancelJob':
      return { path: `${base}/jobs/${id(request.jobId)}/cancel`, method: 'POST' }
    case 'resumeJob':
      return { path: `${base}/jobs/${id(request.jobId)}/resume`, method: 'POST' }
    case 'records':
      return { path: `${base}/jobs/${id(request.jobId)}/records`, method: 'GET' }
    case 'plugins':
      return { path: `${base}/plugins`, method: 'GET' }
    case 'togglePlugin':
      if (!/^[a-z][a-z0-9_-]{0,80}$/.test(request.pluginId)) throw new Error('无效插件')
      return {
        path: `${base}/plugins/${request.pluginId}`,
        method: 'PUT',
        body: { enabled: request.enabled },
      }
    case 'template':
      return {
        path: `${base}/sessions/${id(request.sessionId)}/templates`,
        method: 'POST',
        body: { plugin_id: request.plugin_id },
      }
    case 'results':
      return {
        path: `${base}/jobs/${id(request.jobId)}/results?version=${encodeURIComponent(request.version)}`,
        method: 'GET',
      }
    case 'exportResults':
      if (!['csv', 'xlsx'].includes(request.format)) throw new Error('无效导出格式')
      return {
        path: `${base}/jobs/${id(request.jobId)}/export?version=${encodeURIComponent(request.version)}&format=${request.format}`,
        method: 'GET',
      }
    case 'review':
      return {
        path: `${base}/jobs/${id(request.jobId)}/reviews`,
        method: 'POST',
        body: {
          base_version: request.base_version,
          record_id: request.record_id,
          field_key: request.field_key,
          after: request.after,
          reason: request.reason,
        },
      }
    case 'modelProfile':
      return { path: `${base}/model`, method: 'GET' }
    case 'saveModel':
      return {
        path: `${base}/model`,
        method: 'PUT',
        body: { base_url: request.base_url, model: request.model },
      }
    case 'testModel':
      return { path: `${base}/model/test`, method: 'POST' }
    case 'answers':
      return { path: `${base}/sessions/${id(request.sessionId)}/answers`, method: 'GET' }
    case 'ask':
      return {
        path: `${base}/sessions/${id(request.sessionId)}/answers`,
        method: 'POST',
        body: {
          question: request.question,
          document_ids: request.document_ids,
          request_id: request.request_id,
        },
      }
    case 'parseStatus':
      return { path: `${base}/assets/${id(request.assetId)}/parse`, method: 'GET' }
    case 'parsedContent':
      return { path: `${base}/assets/${id(request.assetId)}/content`, method: 'GET' }
    case 'pdfBytes':
      return { path: `${base}/assets/${id(request.assetId)}/pdf`, method: 'GET', binary: true }
    case 'parseAsset':
      return {
        path: `${base}/assets/${id(request.assetId)}/parse`,
        method: 'POST',
        body: { ocr: request.ocr, force: request.force },
      }
    case 'renameProject':
      return { path: base, method: 'PATCH', body: { name: request.name } }
    case 'deleteProject':
      return { path: base, method: 'DELETE' }
    case 'documents':
      return { path: `${base}/documents`, method: 'GET' }
    case 'sessions':
      return { path: `${base}/sessions`, method: 'GET' }
    case 'scan':
      return { path: `${base}/scan`, method: 'POST' }
    case 'draft':
      return { path: `${base}/scan`, method: 'GET' }
    case 'confirmScan':
      return {
        path: `${base}/scan/confirm`,
        method: 'POST',
        body: { draft_id: request.draft_id, groups: request.groups },
      }
    case 'createSession':
      return { path: `${base}/sessions`, method: 'POST', body: { name: request.name } }
    case 'renameSession':
      return {
        path: `${base}/sessions/${id(request.sessionId)}`,
        method: 'PATCH',
        body: { name: request.name },
      }
    case 'deleteSession':
      return { path: `${base}/sessions/${id(request.sessionId)}`, method: 'DELETE' }
    case 'messages':
      return { path: `${base}/sessions/${id(request.sessionId)}/messages`, method: 'GET' }
    case 'addMessage':
      return {
        path: `${base}/sessions/${id(request.sessionId)}/messages`,
        method: 'POST',
        body: { content: request.content },
      }
    default:
      throw new Error('不支持的操作')
  }
}
