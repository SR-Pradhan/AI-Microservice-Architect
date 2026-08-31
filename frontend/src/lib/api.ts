// Thin wrapper around the orchestrator API. Vite proxies /api -> http://localhost:8000.

const BASE = '/api'

export type StageType = 'boundaries' | 'hld' | 'lld' | 'db_schema' | 'kafka_events' | 'infra'
export type StageStatus = 'pending' | 'generated' | 'edited' | 'approved'

export interface Stage {
  id: string
  stage_type: StageType
  status: StageStatus
  version: number
  output_json: unknown | null
  user_edited_json: unknown | null
  created_at: string
  updated_at: string
}

export interface Project {
  id: string
  name: string
  raw_description: string
  created_at: string
  updated_at: string
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
    throw new Error(`${res.status} ${res.statusText}: ${body}`)
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T)
}

export const api = {
  listProjects: () => request<Project[]>('/projects'),
  getProject: (id: string) => request<ProjectDetail>(`/projects/${id}`),
  createProject: (name: string, raw_description: string) =>
    request<ProjectDetail>('/projects', {
      method: 'POST',
      body: JSON.stringify({ name, raw_description }),
    }),
  deleteProject: (id: string) => request<void>(`/projects/${id}`, { method: 'DELETE' }),
}
