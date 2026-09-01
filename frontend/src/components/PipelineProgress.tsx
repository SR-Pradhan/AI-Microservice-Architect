import type { Stage, StageStatus, StageType } from '../lib/api'

const SHORT: Record<StageType, string> = {
  boundaries: 'Boundaries',
  hld: 'HLD',
  lld: 'LLD',
  db_schema: 'Schemas',
  kafka_events: 'Events',
  infra: 'Infra',
}

const STEP_STYLE: Record<StageStatus, string> = {
  pending: 'border-line bg-surface text-ink-faint',
  generated: 'border-accent/30 bg-accent-soft text-accent',
  edited: 'border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950/60 dark:text-amber-200',
  approved: 'border-emerald-600 bg-emerald-600 text-white dark:border-emerald-500 dark:bg-emerald-600',
}

/** Six-step overview of where a project actually is, at a glance. */
export default function PipelineProgress({
  stages,
  order,
  onJump,
}: {
  stages: Map<StageType, Stage>
  order: StageType[]
  onJump?: (type: StageType) => void
}) {
  const approved = order.filter((t) => stages.get(t)?.status === 'approved').length

  return (
    <div>
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium uppercase tracking-wide text-ink-faint">Pipeline</span>
        <span className="text-xs tabular-nums text-ink-muted">{approved} of {order.length} approved</span>
      </div>
      <ol className="mt-2 flex items-center gap-1">
        {order.map((type, index) => {
          const stage = stages.get(type)
          const status = stage?.status ?? 'pending'
          return (
            <li key={type} className="flex flex-1 items-center gap-1">
              <button
                onClick={() => onJump?.(type)}
                className={`flex w-full flex-col items-start gap-1 rounded-md border px-2.5 py-1.5 text-left transition-colors ${STEP_STYLE[status]} ${onJump ? 'hover:border-accent/50' : ''}`}
              >
                <span className="text-[10px] font-semibold uppercase tracking-wide opacity-70">
                  {index + 1}
                </span>
                <span className="text-xs font-medium">{SHORT[type]}</span>
              </button>
            </li>
          )
        })}
      </ol>
    </div>
  )
}
