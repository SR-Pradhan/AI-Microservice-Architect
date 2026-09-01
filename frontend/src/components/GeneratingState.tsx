import { useEffect, useState } from 'react'
import type { StageType } from '../lib/api'
import { Skeleton } from './ui'

/** Observed durations from real runs. A number beats a spinner: it tells you whether 40 seconds
 *  of silence is normal or a sign something is wrong. */
const TYPICAL_SECONDS: Record<StageType, number> = {
  boundaries: 10,
  hld: 20,
  lld: 55,
  db_schema: 45,
  kafka_events: 35,
  infra: 70,
}

export default function GeneratingState({ stageType }: { stageType: StageType }) {
  const [elapsed, setElapsed] = useState(0)
  const typical = TYPICAL_SECONDS[stageType]

  useEffect(() => {
    const started = Date.now()
    const id = setInterval(() => setElapsed(Math.round((Date.now() - started) / 1000)), 250)
    return () => clearInterval(id)
  }, [])

  const overrun = elapsed > typical * 1.6
  const pct = Math.min(95, (elapsed / typical) * 100)

  return (
    <div className="rounded-md border border-line bg-canvas p-4">
      <div className="flex items-baseline justify-between gap-3">
        <p className="text-sm font-medium text-ink">Generating…</p>
        <p className="text-xs tabular-nums text-ink-muted">
          {elapsed}s <span className="text-ink-faint">/ ~{typical}s typical</span>
        </p>
      </div>

      <div className="mt-2 h-1 overflow-hidden rounded-full bg-line">
        <div
          className="h-full rounded-full bg-accent transition-[width] duration-300"
          style={{ width: `${pct}%` }}
        />
      </div>

      <p className="mt-2 text-xs text-ink-faint">
        {overrun
          ? 'Taking longer than usual — the model may be retrying after a failed validation.'
          : 'The output is validated against the stage schema and the earlier stages before it is stored.'}
      </p>

      <div className="mt-4 space-y-2">
        <Skeleton className="h-3 w-2/3" />
        <Skeleton className="h-3 w-1/2" />
        <Skeleton className="h-3 w-5/6" />
      </div>
    </div>
  )
}
