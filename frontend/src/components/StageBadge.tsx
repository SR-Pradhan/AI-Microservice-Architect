import type { StageStatus } from '../lib/api'

const STYLES: Record<StageStatus, string> = {
  pending: 'bg-slate-100 text-slate-600 border-slate-200',
  generated: 'bg-blue-50 text-blue-700 border-blue-200',
  edited: 'bg-amber-50 text-amber-700 border-amber-200',
  approved: 'bg-emerald-50 text-emerald-700 border-emerald-200',
}

export default function StageBadge({ status }: { status: StageStatus }) {
  return (
    <span className={`rounded-full border px-2.5 py-0.5 text-xs font-medium ${STYLES[status]}`}>
      {status}
    </span>
  )
}
