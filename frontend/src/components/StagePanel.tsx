import { lazy, Suspense, useEffect, useState } from 'react'
import { api, type Stage, type StageType } from '../lib/api'
import StageBadge from './StageBadge'
// Mermaid is ~700kB. Loading it lazily keeps it out of the initial bundle for anyone who never
// opens a diagram.
const MermaidDiagram = lazy(() => import('./MermaidDiagram'))
const LLDView = lazy(() => import('./LLDView'))

/** Stages that render as something friendlier than raw JSON, and what that tab is called. */
const VISUAL_TABS: Partial<Record<StageType, string>> = {
  hld: 'Diagram',
  lld: 'Contracts',
  db_schema: 'ER Diagram',
  kafka_events: 'Event Flow',
}

/** Stages whose visual view is a Mermaid diagram fetched from the backend. */
const DIAGRAM_STAGES: StageType[] = ['hld', 'db_schema', 'kafka_events']

const LABELS: Record<StageType, string> = {
  boundaries: '1. Service Boundaries',
  hld: '2. High-Level Design',
  lld: '3. Low-Level Design',
  db_schema: '4. DB Schemas',
  kafka_events: '5. Kafka Event Contracts',
  infra: '6. Docker / Kubernetes',
}

interface Props {
  projectId: string
  stage: Stage
  /** Stages are gated: this one can only run once the previous one is approved. */
  unlocked: boolean
  onChanged: (stage: Stage) => void
}

export default function StagePanel({ projectId, stage, unlocked, onChanged }: Props) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const [view, setView] = useState<'visual' | 'json'>('json')
  const [mermaid, setMermaid] = useState<string | null>(null)

  const current = stage.user_edited_json ?? stage.output_json
  const hasOutput = current !== null
  const approved = stage.status === 'approved'
  const visualLabel = VISUAL_TABS[stage.stage_type]
  const hasVisual = visualLabel !== undefined
  const needsDiagram = DIAGRAM_STAGES.includes(stage.stage_type)

  // Reset the editor whenever the server hands us new content, so the textarea never shows a
  // stale draft from a previous generation.
  useEffect(() => {
    setDraft(current ? JSON.stringify(current, null, 2) : '')
    if (hasVisual && current) setView('visual')
  }, [current, hasVisual])

  // The diagram is built server-side, so it always reflects what is actually stored.
  useEffect(() => {
    if (!open || !needsDiagram || !hasOutput) return
    let cancelled = false
    api
      .getStageDiagram(projectId, stage.stage_type)
      .then((d) => !cancelled && setMermaid(d.mermaid))
      .catch(() => !cancelled && setMermaid(null))
    return () => {
      cancelled = true
    }
  }, [open, needsDiagram, hasOutput, projectId, stage.stage_type, stage.version, current])

  async function act(label: string, fn: () => Promise<Stage>) {
    setBusy(label)
    setError(null)
    try {
      onChanged(await fn())
      setOpen(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(null)
    }
  }

  function handleSave() {
    let parsed: unknown
    try {
      parsed = JSON.parse(draft)
    } catch {
      setError('That is not valid JSON.')
      return
    }
    act('save', () => api.saveStageEdit(projectId, stage.stage_type, parsed))
  }

  return (
    <li className="p-4">
      <div className="flex items-center justify-between gap-3">
        <button
          onClick={() => setOpen((o) => !o)}
          className="text-left text-sm font-medium text-slate-800 hover:underline"
        >
          {LABELS[stage.stage_type]}
          {stage.version > 0 && (
            <span className="ml-2 text-xs font-normal text-slate-400">v{stage.version}</span>
          )}
        </button>
        <div className="flex items-center gap-2">
          <StageBadge status={stage.status} />
          {!approved && unlocked && (
            <button
              onClick={() => act('run', () => api.runStage(projectId, stage.stage_type))}
              disabled={busy !== null}
              className="rounded bg-slate-900 px-3 py-1 text-xs font-medium text-white disabled:opacity-50"
            >
              {busy === 'run' ? 'Generating...' : stage.version > 0 ? 'Regenerate' : 'Generate'}
            </button>
          )}
          {!approved && hasOutput && (
            <button
              onClick={() => act('approve', () => api.approveStage(projectId, stage.stage_type))}
              disabled={busy !== null}
              className="rounded border border-emerald-600 px-3 py-1 text-xs font-medium text-emerald-700 disabled:opacity-50"
            >
              Approve
            </button>
          )}
          {approved && (
            <button
              onClick={() => act('unapprove', () => api.unapproveStage(projectId, stage.stage_type))}
              disabled={busy !== null}
              className="rounded border border-slate-300 px-3 py-1 text-xs font-medium text-slate-600 disabled:opacity-50"
            >
              Unlock
            </button>
          )}
        </div>
      </div>

      {!unlocked && !hasOutput && (
        <p className="mt-2 text-xs text-slate-400">Approve the previous stage to unlock this one.</p>
      )}
      {error && <p className="mt-2 text-xs text-red-600">{error}</p>}

      {open && hasOutput && (
        <div className="mt-3">
          {hasVisual && (
            <div className="mb-2 flex gap-1">
              {(['visual', 'json'] as const).map((v) => (
                <button
                  key={v}
                  onClick={() => setView(v)}
                  className={`rounded px-2.5 py-1 text-xs font-medium ${
                    view === v ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-100'
                  }`}
                >
                  {v === 'visual' ? visualLabel : 'JSON'}
                </button>
              ))}
            </div>
          )}

          {hasVisual && view === 'visual' ? (
            <Suspense fallback={<p className="text-xs text-slate-400">Loading...</p>}>
              {needsDiagram ? (
                mermaid ? (
                  <MermaidDiagram code={mermaid} />
                ) : (
                  <p className="text-xs text-slate-400">Loading diagram...</p>
                )
              ) : (
                <LLDView data={current} />
              )}
            </Suspense>
          ) : (
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              readOnly={approved}
              spellCheck={false}
              className="h-80 w-full rounded border border-slate-300 bg-slate-50 p-3 font-mono text-xs text-slate-800 read-only:opacity-70"
            />
          )}
          {!approved && view === 'json' && (
            <div className="mt-2 flex items-center gap-2">
              <button
                onClick={handleSave}
                disabled={busy !== null}
                className="rounded border border-slate-300 px-3 py-1 text-xs font-medium text-slate-700 disabled:opacity-50"
              >
                {busy === 'save' ? 'Saving...' : 'Save edits'}
              </button>
              <span className="text-xs text-slate-400">
                Your edit is validated against the stage schema before it is stored.
              </span>
            </div>
          )}
        </div>
      )}
    </li>
  )
}
