export interface HealthStatus {
  status: 'ok'
  service: string
  version: string
  database: string
  migration: string
}
export interface DesktopBridge {
  watchJob?: (
    projectId: string,
    jobId: string,
    callback: (value: JobDetail | { error: string }) => void,
  ) => () => void
  health: () => Promise<HealthStatus>
  chooseFolder: () => Promise<string | null>
  request: (request: WorkspaceRequest) => Promise<unknown>
}

export interface Project {
  id: string
  name: string
  source_path: string
  revision: number
  created_at: string
  scanned_at: string | null
}
export interface Conversation {
  id: string
  project_id: string
  name: string
  created_at: string
}
export interface Note {
  id: string
  project_id: string
  session_id: string
  content: string
  created_at: string
  role: 'note'
}
export interface Asset {
  id: string
  relative_path: string
  absolute_path: string
  size: number
  mtime_ns: number
  sha256: string
  kind: string
  role: string
  status: string
}
export interface Document {
  id: string
  project_id: string
  title: string
  main_path: string | null
  status: string
  assets: Asset[]
}
export interface ScanGroup {
  key: string
  title: string
  main_path: string | null
  asset_paths: string[]
  confidence: 'high' | 'review'
  reason: string
}
export interface ScanDraft {
  id: string
  project_id: string
  base_revision: number
  created_at: string
  snapshot: { assets: Asset[]; groups: ScanGroup[]; warnings: string[] }
}
export type ConfirmGroup = Pick<ScanGroup, 'title' | 'main_path' | 'asset_paths'>
export type WorkspaceRequest =
  | { action: 'plugins'; projectId: string }
  | { action: 'togglePlugin'; projectId: string; pluginId: string; enabled: boolean }
  | { action: 'template'; projectId: string; sessionId: string; plugin_id: string }
  | { action: 'results'; projectId: string; jobId: string; version: string }
  | {
      action: 'exportResults'
      projectId: string
      jobId: string
      version: string
      format: 'csv' | 'xlsx'
    }
  | {
      action: 'review'
      projectId: string
      jobId: string
      base_version: number
      record_id: string
      field_key: string
      after: ResultRecord['values_json'][string]
      reason: string
    }
  | { action: 'route'; projectId: string; text: string }
  | { action: 'plans' | 'jobs'; projectId: string; sessionId: string }
  | { action: 'design'; projectId: string; sessionId: string; goal: string; document_ids: string[] }
  | {
      action: 'confirmPlan'
      projectId: string
      sessionId: string
      schema_id: string
      request_id: string
      plan: ExtractionPlan
    }
  | { action: 'job' | 'cancelJob' | 'resumeJob' | 'records'; projectId: string; jobId: string }
  | { action: 'modelProfile' | 'testModel' | 'deleteModelKey'; projectId: string }
  | { action: 'saveModel'; projectId: string; base_url: string; model: string; apiKey: string }
  | { action: 'answers'; projectId: string; sessionId: string }
  | {
      action: 'ask'
      projectId: string
      sessionId: string
      question: string
      document_ids: string[]
      request_id: string
    }
  | { action: 'parseStatus' | 'parsedContent' | 'pdfBytes'; projectId: string; assetId: string }
  | { action: 'parseAsset'; projectId: string; assetId: string; ocr: boolean; force: boolean }
  | { action: 'projects' }
  | { action: 'createProject'; name: string; source_path: string }
  | { action: 'renameProject'; projectId: string; name: string }
  | { action: 'deleteProject' | 'documents' | 'sessions' | 'scan' | 'draft'; projectId: string }
  | { action: 'confirmScan'; projectId: string; draft_id: string; groups: ConfirmGroup[] }
  | { action: 'createSession'; projectId: string; name: string }
  | { action: 'renameSession'; projectId: string; sessionId: string; name: string }
  | { action: 'deleteSession' | 'messages'; projectId: string; sessionId: string }
  | { action: 'addMessage'; projectId: string; sessionId: string; content: string }

export interface ParseStatus {
  asset_id: string
  status: 'unparsed' | 'queued' | 'running' | 'ready' | 'failed' | 'stale' | 'interrupted'
  run_id?: string
  source_sha256?: string
  parser_version?: string
  ocr?: boolean
  error?: string | null
}
export interface SourceLocation {
  page: number
  bbox: [number, number, number, number] | null
}
export interface TableCell {
  text: string
  row: number
  column: number
  row_span: number
  column_span: number
  header: boolean
}
export interface DocumentBlock {
  id: string
  kind: 'heading' | 'text' | 'table' | 'picture'
  text: string
  label: string
  level: number
  section: string
  locations: SourceLocation[]
  cells: TableCell[]
  rows: number
  columns: number
}
export interface ParsedContent {
  format_version: number
  parser: string
  parser_version: string
  source_sha256: string
  asset_id: string
  filename: string
  pages: { number: number; width: number; height: number }[]
  blocks: DocumentBlock[]
  warnings: string[]
}

export interface ModelProfile {
  base_url: string
  model: string
  hasKey: boolean
}
export interface Evidence {
  id: string
  document_id: string
  asset_id: string
  filename: string
  source_sha256: string
  block_id: string
  quote: string
  locations: SourceLocation[]
  kind: string
}
export interface ChatRun {
  id: string
  question: string
  status: 'running' | 'complete' | 'failed'
  error: string | null
  answer: {
    parts: { text: string; evidence_ids: string[]; kind: string }[]
    evidence: Evidence[]
    warnings: string[]
  } | null
}
export interface PlanField {
  key: string
  label: string
  description: string
  type: 'string' | 'number' | 'boolean'
  unit: string
  minimum?: number | null
  maximum?: number | null
}
export interface ExtractionPlan {
  plugins?: { id: string; version: string }[]
  name: string
  granularity: string
  fields: PlanField[]
  record_key: string[]
  missing_policy: string
  conflict_policy: string
  evidence_policy: string
}
export interface PlanVersion {
  id: string
  version: number
  status: string
  goal: string
  plan: ExtractionPlan
  document_ids: string[]
}
export interface Job {
  id: string
  status: string
  schema_id: string
  error: string | null
}
export interface JobDetail extends Job {
  documents: { document_id: string; status: string; error: string | null; warnings: string[] }[]
  schema: PlanVersion
  record_count: number
}
export interface ResultRecord {
  id: string
  project_id: string
  job_id: string
  document_id: string
  values_json: Record<
    string,
    {
      value: string | number | boolean | null
      unit: string
      missing_reason: string
      evidence_ids: string[]
      standardized?: { value: string | number; unit: string; note: string } | null
    }
  >
  evidence_json: Evidence[]
  risks: string[]
}
export interface ReviewRevision {
  id: string
  version: number
  record_id: string
  field_key: string
  before: ResultRecord['values_json'][string]
  after: ResultRecord['values_json'][string]
  reason: string
  created_at: string
}
export interface ResultSnapshot {
  records: ResultRecord[]
  history: ReviewRevision[]
  version: number
  latest_version: number
  schema: PlanVersion
  job: Job
}
export interface DomainPlugin {
  id: string
  name: string
  version: string
  enabled: boolean
  configured_version: string | null
  description: string
  context: { templates: ExtractionPlan[]; synonyms: Record<string, string[]>[]; rules: string[] }
}
