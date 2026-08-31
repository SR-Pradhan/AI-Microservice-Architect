import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, type ProjectDetail, type StageType } from '../lib/api'
import StageBadge from '../components/StageBadge'

const STAGE_LABELS: Record<StageType, string> = {
  boundaries: '1. Service Boundaries',
  hld: '2. High-Level Design',
  lld: '3. Low-Level Design',
  db_schema: '4. DB Schemas',
  kafka_events: '5. Kafka Event Contracts',
  infra: '6. Docker / Kubernetes',
}

const STAGE_ORDER: StageType[] = ['boundaries', 'hld', 'lld', 'db_schema', 'kafka_events', 'infra']

export default function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [project, setProject] = useState<ProjectDetail | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (id) api.getProject(id).then(setProject).catch((e) => setError(String(e)))
  }, [id])

  if (error) return <p className="p-8 text-sm text-red-600">{error}</p>
  if (!project) return <p className="p-8 text-sm text-slate-500">Loading...</p>

  const byType = new Map(project.stages.map((s) => [s.stage_type, s]))

  return (
    <div className="mx-auto max-w-3xl p-8">
      <Link to="/" className="text-sm text-slate-500 hover:underline">
        &larr; All projects
      </Link>
      <h1 className="mt-3 text-2xl font-semibold text-slate-900">{project.name}</h1>
      <p className="mt-2 whitespace-pre-wrap text-sm text-slate-600">{project.raw_description}</p>

      <h2 className="mt-8 text-sm font-semibold uppercase tracking-wide text-slate-500">Pipeline</h2>
      <ul className="mt-3 divide-y divide-slate-200 rounded-lg border border-slate-200">
        {STAGE_ORDER.map((type) => {
          const stage = byType.get(type)
          return (
            <li key={type} className="flex items-center justify-between p-4">
              <span className="text-sm font-medium text-slate-800">{STAGE_LABELS[type]}</span>
              {stage ? <StageBadge status={stage.status} /> : null}
            </li>
          )
        })}
      </ul>
      <p className="mt-4 text-xs text-slate-400">
        Generation lands in v0.2.0 — right now every stage starts out pending.
      </p>
    </div>
  )
}
