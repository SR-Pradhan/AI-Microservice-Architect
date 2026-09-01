import type { StageStatus } from '../lib/api'

const STYLES: Record<StageStatus, { label: string; className: string; dot: string }> = {
  pending: { label: 'Pending', className: 'bg-canvas text-ink-faint border-line', dot: 'bg-ink-faint' },
  generated: { label: 'Generated', className: 'bg-accent-soft text-accent border-accent/25', dot: 'bg-accent' },
  edited: { label: 'Edited', className: 'bg-amber-50 text-amber-800 border-amber-200 dark:bg-amber-950/60 dark:text-amber-200 dark:border-amber-900', dot: 'bg-amber-500' },
  approved: { label: 'Approved', className: 'bg-emerald-50 text-emerald-800 border-emerald-200 dark:bg-emerald-950/60 dark:text-emerald-200 dark:border-emerald-900', dot: 'bg-emerald-500' },
}

export default function StageBadge({ status }: { status: StageStatus }) {
  const style = STYLES[status]
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${style.className}`}
    >
      <span aria-hidden className={`h-1.5 w-1.5 rounded-full ${style.dot}`} />
      {style.label}
    </span>
  )
}
