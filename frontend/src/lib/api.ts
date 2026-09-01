// Thin wrapper around the orchestrator API. Vite proxies /api -> http://localhost:8000.

const BASE = '/api'

export type StageType = 'boundaries' | 'hld' | 'lld' | 'db_schema' | 'kafka_events' | 'infra'
export type StageStatus = 'pending' | 'generated' | 'edited' | 'approved'

export interface Stage {
  id: string
  stage_type: StageType
  status: StageStatus
  version: number
  output_json: Record<string, unknown> | null
  user_edited_json: Record<string, unknown> | null
  created_at: string
  updated_at: string
}

export interface Project {
  id: string
  name: string
  raw_description: string
  created_at: string
  updated_at: string
  /** Stage statuses in pipeline order — lets the list show progress without a second request. */
  stage_statuses: StageStatus[]
}

export interface ProjectDetail extends Project {
  stages: Stage[]
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    const body = await res.text()
    // FastAPI puts the human-readable reason in `detail`; fall back to the raw body.
    let message = body
    try {
      const parsed = JSON.parse(body)
      if (typeof parsed.detail === 'string') message = parsed.detail
    } catch {
      /* body was not JSON — use it as-is */
    }
    throw new Error(message)
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T)
}

export const api = {
  exportUrl: (projectId: string) => `${BASE}/projects/${projectId}/export`,
  runStage: (projectId: string, stage: StageType) =>
    request<Stage>(`/projects/${projectId}/stages/${stage}/run`, { method: 'POST' }),
  saveStageEdit: (projectId: string, stage: StageType, output_json: unknown) =>
    request<Stage>(`/projects/${projectId}/stages/${stage}`, {
      method: 'PUT',
      body: JSON.stringify({ output_json }),
    }),
  getStageDiagram: (projectId: string, stage: StageType) =>
    request<{ mermaid: string }>(`/projects/${projectId}/stages/${stage}/diagram`),
  approveStage: (projectId: string, stage: StageType) =>
    request<Stage>(`/projects/${projectId}/stages/${stage}/approve`, { method: 'POST' }),
  unapproveStage: (projectId: string, stage: StageType) =>
    request<Stage>(`/projects/${projectId}/stages/${stage}/unapprove`, { method: 'POST' }),
  listProjects: () => request<Project[]>('/projects'),
  getProject: (id: string) => request<ProjectDetail>(`/projects/${id}`),
  createProject: (name: string, raw_description: string) =>
    request<ProjectDetail>('/projects', {
      method: 'POST',
      body: JSON.stringify({ name, raw_description }),
    }),
  deleteProject: (id: string) => request<void>(`/projects/${id}`, { method: 'DELETE' }),
}
