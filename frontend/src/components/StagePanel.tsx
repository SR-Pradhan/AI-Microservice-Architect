import { useEffect, useState } from 'react'
import { api, type Stage, type StageType } from '../lib/api'
import StageBadge from './StageBadge'

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

  const current = stage.user_edited_json ?? stage.output_json
  const hasOutput = current !== null
  const approved = stage.status === 'approved'

  // Reset the editor whenever the server hands us new content, so the textarea never shows a
  // stale draft from a previous generation.
  useEffect(() => {
    setDraft(current ? JSON.stringify(current, null, 2) : '')
  }, [current])

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
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            readOnly={approved}
            spellCheck={false}
            className="h-80 w-full rounded border border-slate-300 bg-slate-50 p-3 font-mono text-xs text-slate-800 read-only:opacity-70"
          />
          {!approved && (
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
