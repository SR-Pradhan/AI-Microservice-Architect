import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, type ProjectDetail, type Stage, type StageType } from '../lib/api'
import AppShell from '../components/AppShell'
import PipelineProgress from '../components/PipelineProgress'
import StagePanel from '../components/StagePanel'
import { Alert, Card, Skeleton } from '../components/ui'

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

  if (error) {
    return (
      <AppShell>
        <Alert>{error}</Alert>
      </AppShell>
    )
  }

  if (!project || !id) {
    return (
      <AppShell>
        <Skeleton className="h-7 w-72" />
        <Skeleton className="mt-3 h-4 w-full max-w-2xl" />
        <Skeleton className="mt-8 h-16 w-full" />
        <Skeleton className="mt-4 h-72 w-full" />
      </AppShell>
    )
  }

  const byType = new Map(project.stages.map((s) => [s.stage_type, s]))
  const anyGenerated = project.stages.some((s) => s.output_json || s.user_edited_json)

  function jumpTo(type: StageType) {
    document.getElementById(`stage-${type}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }

  return (
    <AppShell>
      <Link to="/" className="text-sm text-ink-muted hover:text-ink">
        ← All projects
      </Link>

      <div className="mt-3 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-3xl font-semibold tracking-tight text-ink">{project.name}</h1>
          <p className="mt-2.5 max-w-3xl whitespace-pre-wrap text-sm leading-relaxed text-ink-muted">
            {project.raw_description}
          </p>
        </div>
        {/* A plain link, not fetch(): the browser handles the download and Content-Disposition. */}
        <a
          href={api.exportUrl(project.id)}
          className={`shrink-0 rounded-md px-3.5 py-2 text-sm font-medium transition-colors ${
            anyGenerated
              ? 'bg-accent text-white hover:bg-accent-hover'
              : 'pointer-events-none border border-line bg-canvas text-ink-faint'
          }`}
          aria-disabled={!anyGenerated}
        >
          Download scaffold
        </a>
      </div>

      <Card className="mt-6 p-4">
        <PipelineProgress stages={byType} order={STAGE_ORDER} onJump={jumpTo} />
      </Card>

      <Card className="mt-4 overflow-hidden">
        <ul className="divide-y divide-line">
          {STAGE_ORDER.map((type, index) => {
            const stage = byType.get(type)
            if (!stage) return null
            // Stage 1 is always unlocked; every later stage needs its predecessor approved.
            const previous = index === 0 ? null : byType.get(STAGE_ORDER[index - 1])
            const unlocked = index === 0 || previous?.status === 'approved'
            return (
              <StagePanel
                key={stage.id}
                index={index}
                projectId={id}
                stage={stage}
                unlocked={unlocked}
                onChanged={handleStageChanged}
              />
            )
          })}
        </ul>
      </Card>
    </AppShell>
  )
}
