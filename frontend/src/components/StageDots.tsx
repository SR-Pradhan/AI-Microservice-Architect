import type { StageStatus } from '../lib/api'

const DOT: Record<StageStatus, string> = {
  pending: 'bg-line',
  generated: 'bg-accent',
  edited: 'bg-amber-500',
  approved: 'bg-emerald-500',
}

const STAGE_NAMES = ['Boundaries', 'HLD', 'LLD', 'Schemas', 'Events', 'Infra']

/** Six dots showing how far a project has got, at list-view size. */
export default function StageDots({ statuses }: { statuses: StageStatus[] }) {
  const done = statuses.filter((s) => s === 'approved').length
  const started = statuses.some((s) => s !== 'pending')

  return (
    <div className="flex items-center gap-2">
      <div className="flex gap-1">
        {statuses.map((status, i) => (
          <span
            key={i}
            title={`${STAGE_NAMES[i]}: ${status}`}
            className={`h-1.5 w-6 rounded-full transition-colors ${DOT[status]}`}
          />
        ))}
      </div>
      <span className="text-xs tabular-nums text-ink-faint">
        {started ? `${done}/6` : 'Not started'}
      </span>
    </div>
  )
}
