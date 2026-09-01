import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, type ProjectDetail, type Stage, type StageType } from '../lib/api'
import StagePanel from '../components/StagePanel'

const STAGE_ORDER: StageType[] = ['boundaries', 'hld', 'lld', 'db_schema', 'kafka_events', 'infra']

export default function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [project, setProject] = useState<ProjectDetail | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (id) api.getProject(id).then(setProject).catch((e) => setError(String(e)))
  }, [id])

  function handleStageChanged(updated: Stage) {
    setProject((p) =>
      p ? { ...p, stages: p.stages.map((s) => (s.id === updated.id ? updated : s)) } : p,
    )
  }

  if (error) return <p className="p-8 text-sm text-red-600">{error}</p>
  if (!project || !id) return <p className="p-8 text-sm text-slate-500">Loading...</p>

  const byType = new Map(project.stages.map((s) => [s.stage_type, s]))

  return (
    <div className="mx-auto max-w-7xl p-8">
      <Link to="/" className="text-sm text-slate-500 hover:underline">
        &larr; All projects
      </Link>
      <h1 className="mt-3 text-2xl font-semibold text-slate-900">{project.name}</h1>
      <p className="mt-2 max-w-3xl whitespace-pre-wrap text-sm text-slate-600">
        {project.raw_description}
      </p>

      <h2 className="mt-8 text-sm font-semibold uppercase tracking-wide text-slate-500">Pipeline</h2>
      <ul className="mt-3 divide-y divide-slate-200 rounded-lg border border-slate-200">
        {STAGE_ORDER.map((type, index) => {
          const stage = byType.get(type)
          if (!stage) return null
          // Stage 1 is always unlocked; every later stage needs its predecessor approved.
          const previous = index === 0 ? null : byType.get(STAGE_ORDER[index - 1])
          const unlocked = index === 0 || previous?.status === 'approved'
          return (
            <StagePanel
              key={stage.id}
              projectId={id}
              stage={stage}
              unlocked={unlocked}
              onChanged={handleStageChanged}
            />
          )
        })}
      </ul>
      <p className="mt-4 text-xs text-slate-400">
        Stage 1 is live. Stages 2-6 return "not implemented yet" until later versions.
      </p>
    </div>
  )
}
