/** Readable view of a Stage 3 LLD: per-service entities and API contracts. */

interface DataField {
  name: string
  type: string
  required: boolean
  description: string
}

interface Endpoint {
  method: string
  path: string
  summary: string
  request_fields: DataField[]
  response_fields: DataField[]
  called_by: string[]
}

interface ServiceLLD {
  name: string
  tech_stack: string
  entities: { name: string; description: string; fields: DataField[] }[]
  endpoints: Endpoint[]
  published_events: string[]
  consumed_events: string[]
  internal_logic_notes: string
}

const METHOD_COLORS: Record<string, string> = {
  GET: 'bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-200',
  POST: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200',
  PUT: 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-200',
  PATCH: 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-200',
  DELETE: 'bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-200',
}

function FieldTable({ title, fields }: { title: string; fields: DataField[] }) {
  if (fields.length === 0) return null
  return (
    <div className="mt-2">
      <p className="text-xs font-medium text-ink-muted">{title}</p>
      <table className="mt-1 w-full text-left text-xs">
        <tbody className="divide-y divide-line">
          {fields.map((f) => (
            <tr key={f.name}>
              <td className="py-1 pr-3 font-mono text-ink">{f.name}</td>
              <td className="py-1 pr-3 text-ink-muted">{f.type}</td>
              <td className="py-1 pr-3 text-ink-faint">{f.required ? 'required' : 'optional'}</td>
              <td className="py-1 text-ink-muted">{f.description}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function LLDView({ data }: { data: Record<string, unknown> }) {
  const services = (data.services ?? []) as ServiceLLD[]

  return (
    <div className="space-y-4">
      {services.map((service) => (
        <div key={service.name} className="rounded-card border border-line bg-surface p-4">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h3 className="text-sm font-semibold text-ink">{service.name}</h3>
            <span className="text-xs text-ink-muted">{service.tech_stack}</span>
          </div>

          {(service.published_events.length > 0 || service.consumed_events.length > 0) && (
            <div className="mt-2 flex flex-wrap gap-1">
              {service.published_events.map((e) => (
                <span key={`p-${e}`} className="rounded bg-accent-soft px-2 py-0.5 font-mono text-xs text-accent">
                  ↑ {e}
                </span>
              ))}
              {service.consumed_events.map((e) => (
                <span key={`c-${e}`} className="rounded bg-canvas px-2 py-0.5 font-mono text-xs text-ink-muted">
                  ↓ {e}
                </span>
              ))}
            </div>
          )}

          <p className="mt-3 text-xs font-medium uppercase tracking-wide text-ink-faint">Endpoints</p>
          <div className="mt-1 space-y-3">
            {service.endpoints.map((endpoint) => (
              <div key={`${endpoint.method} ${endpoint.path}`} className="rounded bg-canvas p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span
                    className={`rounded px-1.5 py-0.5 font-mono text-xs font-semibold ${
                      METHOD_COLORS[endpoint.method] ?? 'bg-line text-ink-muted'
                    }`}
                  >
                    {endpoint.method}
                  </span>
                  <span className="font-mono text-xs text-ink">{endpoint.path}</span>
                  {endpoint.called_by.length > 0 && (
                    <span className="text-xs text-ink-faint">
                      called by {endpoint.called_by.join(', ')}
                    </span>
                  )}
                </div>
                <p className="mt-1 text-xs text-ink-muted">{endpoint.summary}</p>
                <FieldTable title="Request" fields={endpoint.request_fields} />
                <FieldTable title="Response" fields={endpoint.response_fields} />
              </div>
            ))}
          </div>

          <p className="mt-4 text-xs font-medium uppercase tracking-wide text-ink-faint">Entities</p>
          <div className="mt-1 space-y-2">
            {service.entities.map((entity) => (
              <div key={entity.name}>
                <p className="text-xs font-semibold text-ink">{entity.name}</p>
                <p className="text-xs text-ink-muted">{entity.description}</p>
                <FieldTable title="" fields={entity.fields} />
              </div>
            ))}
          </div>

          <p className="mt-4 text-xs font-medium uppercase tracking-wide text-ink-faint">Notes</p>
          <p className="mt-1 whitespace-pre-wrap text-xs text-ink-muted">
            {service.internal_logic_notes}
          </p>
        </div>
      ))}
    </div>
  )
}
