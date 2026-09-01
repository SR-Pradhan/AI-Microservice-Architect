import { lazy, Suspense, useEffect, useState } from 'react'
import { api, type Stage, type StageType } from '../lib/api'
import StageBadge from './StageBadge'
import GeneratingState from './GeneratingState'
import { Alert, Button, inputClass } from './ui'

// Mermaid is ~700kB. Loading these lazily keeps them out of the initial bundle for anyone who
// never opens a diagram.
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

const LABELS: Record<StageType, { title: string; blurb: string }> = {
  boundaries: { title: 'Service Boundaries', blurb: 'Which services exist, and why' },
  hld: { title: 'High-Level Design', blurb: 'Service map, sync vs async, datastores' },
  lld: { title: 'Low-Level Design', blurb: 'Entities, API contracts, internal logic' },
  db_schema: { title: 'DB Schemas', blurb: 'Tables, columns, indexes, keys' },
  kafka_events: { title: 'Kafka Event Contracts', blurb: 'Topics, partitions, consumer groups' },
  infra: { title: 'Docker / Kubernetes', blurb: 'Images, ports, probes, resources' },
}

interface Props {
  index: number
  projectId: string
  stage: Stage
  /** Stages are gated: this one can only run once the previous one is approved. */
  unlocked: boolean
  onChanged: (stage: Stage) => void
}

export default function StagePanel({ index, projectId, stage, unlocked, onChanged }: Props) {
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
  const dirty = hasOutput && draft !== JSON.stringify(current, null, 2)

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

  const label = LABELS[stage.stage_type]
  const locked = !unlocked && !hasOutput

  return (
    <li id={`stage-${stage.stage_type}`} className={locked ? 'opacity-60' : ''}>
      <div className="flex flex-wrap items-center gap-3 px-4 py-3.5">
        <button
          onClick={() => hasOutput && setOpen((o) => !o)}
          disabled={!hasOutput}
          className="flex min-w-0 flex-1 items-center gap-3 text-left disabled:cursor-default"
        >
          <span
            aria-hidden
            className="grid h-7 w-7 shrink-0 place-items-center rounded-md border border-line bg-canvas text-xs font-semibold text-ink-muted"
          >
            {index + 1}
          </span>
          <span className="min-w-0">
            <span className="flex items-center gap-2">
              <span className="truncate text-sm font-medium text-ink">{label.title}</span>
              {stage.version > 0 && (
                <span className="shrink-0 rounded bg-canvas px-1.5 py-0.5 text-[10px] font-medium text-ink-faint">
                  v{stage.version}
                </span>
              )}
              {hasOutput && (
                <span aria-hidden className="text-ink-faint">
                  {open ? '▾' : '▸'}
                </span>
              )}
            </span>
            <span className="block truncate text-xs text-ink-faint">{label.blurb}</span>
          </span>
        </button>

        <div className="flex shrink-0 items-center gap-2">
          <StageBadge status={stage.status} />
          {!approved && unlocked && (
            <Button
              variant="primary"
              size="sm"
              onClick={() => act('run', () => api.runStage(projectId, stage.stage_type))}
              disabled={busy !== null}
            >
              {busy === 'run' ? 'Generating…' : stage.version > 0 ? 'Regenerate' : 'Generate'}
            </Button>
          )}
          {!approved && hasOutput && (
            <Button
              size="sm"
              onClick={() => act('approve', () => api.approveStage(projectId, stage.stage_type))}
              disabled={busy !== null}
              className="border-emerald-400 text-emerald-700 hover:bg-emerald-50 dark:border-emerald-800 dark:text-emerald-300 dark:hover:bg-emerald-950"
            >
              Approve
            </Button>
          )}
          {approved && (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => act('unapprove', () => api.unapproveStage(projectId, stage.stage_type))}
              disabled={busy !== null}
            >
              Unlock
            </Button>
          )}
        </div>
      </div>

      {(locked || error || busy === 'run') && (
        <div className="space-y-2 px-4 pb-4">
          {locked && (
            <p className="text-xs text-ink-faint">
              Approve the previous stage to unlock this one.
            </p>
          )}
          {busy === 'run' && <GeneratingState stageType={stage.stage_type} />}
          {error && <Alert onDismiss={() => setError(null)}>{error}</Alert>}
        </div>
      )}

      {open && hasOutput && (
        <div className="border-t border-line bg-canvas/60 p-4">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            {hasVisual && (
              <div className="inline-flex rounded-md border border-line bg-surface p-0.5">
                {(['visual', 'json'] as const).map((v) => (
                  <button
                    key={v}
                    onClick={() => setView(v)}
                    className={`rounded px-2.5 py-1 text-xs font-medium transition-colors ${
                      view === v ? 'bg-ink text-white' : 'text-ink-muted hover:text-ink'
                    }`}
                  >
                    {v === 'visual' ? visualLabel : 'JSON'}
                  </button>
                ))}
              </div>
            )}
            {view === 'json' && !approved && (
              <div className="ml-auto flex items-center gap-2">
                {dirty && <span className="text-xs text-amber-700 dark:text-amber-400">Unsaved changes</span>}
                <Button size="sm" onClick={handleSave} disabled={busy !== null || !dirty}>
                  {busy === 'save' ? 'Saving…' : 'Save edits'}
                </Button>
              </div>
            )}
          </div>

          {hasVisual && view === 'visual' ? (
            <Suspense fallback={<div className="p-6 text-xs text-ink-faint">Loading…</div>}>
              {needsDiagram ? (
                mermaid ? (
                  <MermaidDiagram code={mermaid} />
                ) : (
                  <div className="p-6 text-xs text-ink-faint">Loading diagram…</div>
                )
              ) : (
                <LLDView data={current} />
              )}
            </Suspense>
          ) : (
            <>
              <textarea
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                readOnly={approved}
                spellCheck={false}
                className={`mono h-96 w-full resize-y leading-relaxed ${inputClass} read-only:bg-canvas read-only:text-ink-muted`}
              />
              {!approved && (
                <p className="mt-1.5 text-xs text-ink-faint">
                  Edits are validated against the stage schema, and against the earlier stages,
                  before they are stored.
                </p>
              )}
            </>
          )}
        </div>
      )}
    </li>
  )
}
