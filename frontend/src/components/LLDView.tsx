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
  GET: 'bg-sky-100 text-sky-800',
  POST: 'bg-emerald-100 text-emerald-800',
  PUT: 'bg-amber-100 text-amber-800',
  PATCH: 'bg-amber-100 text-amber-800',
  DELETE: 'bg-red-100 text-red-800',
}

function FieldTable({ title, fields }: { title: string; fields: DataField[] }) {
  if (fields.length === 0) return null
  return (
    <div className="mt-2">
      <p className="text-xs font-medium text-slate-500">{title}</p>
      <table className="mt-1 w-full text-left text-xs">
        <tbody className="divide-y divide-slate-100">
          {fields.map((f) => (
            <tr key={f.name}>
              <td className="py-1 pr-3 font-mono text-slate-800">{f.name}</td>
              <td className="py-1 pr-3 text-slate-500">{f.type}</td>
              <td className="py-1 pr-3 text-slate-400">{f.required ? 'required' : 'optional'}</td>
              <td className="py-1 text-slate-500">{f.description}</td>
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
        <div key={service.name} className="rounded border border-slate-200 p-4">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h3 className="text-sm font-semibold text-slate-900">{service.name}</h3>
            <span className="text-xs text-slate-500">{service.tech_stack}</span>
          </div>

          {(service.published_events.length > 0 || service.consumed_events.length > 0) && (
            <div className="mt-2 flex flex-wrap gap-1">
              {service.published_events.map((e) => (
                <span key={`p-${e}`} className="rounded bg-indigo-50 px-2 py-0.5 font-mono text-xs text-indigo-700">
                  ↑ {e}
                </span>
              ))}
              {service.consumed_events.map((e) => (
                <span key={`c-${e}`} className="rounded bg-slate-100 px-2 py-0.5 font-mono text-xs text-slate-600">
                  ↓ {e}
                </span>
              ))}
            </div>
          )}

          <p className="mt-3 text-xs font-medium uppercase tracking-wide text-slate-400">Endpoints</p>
          <div className="mt-1 space-y-3">
            {service.endpoints.map((endpoint) => (
              <div key={`${endpoint.method} ${endpoint.path}`} className="rounded bg-slate-50 p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span
                    className={`rounded px-1.5 py-0.5 font-mono text-xs font-semibold ${
                      METHOD_COLORS[endpoint.method] ?? 'bg-slate-200 text-slate-700'
                    }`}
                  >
                    {endpoint.method}
                  </span>
                  <span className="font-mono text-xs text-slate-800">{endpoint.path}</span>
                  {endpoint.called_by.length > 0 && (
                    <span className="text-xs text-slate-400">
                      called by {endpoint.called_by.join(', ')}
                    </span>
                  )}
                </div>
                <p className="mt-1 text-xs text-slate-600">{endpoint.summary}</p>
                <FieldTable title="Request" fields={endpoint.request_fields} />
                <FieldTable title="Response" fields={endpoint.response_fields} />
              </div>
            ))}
          </div>

          <p className="mt-4 text-xs font-medium uppercase tracking-wide text-slate-400">Entities</p>
          <div className="mt-1 space-y-2">
            {service.entities.map((entity) => (
              <div key={entity.name}>
                <p className="text-xs font-semibold text-slate-800">{entity.name}</p>
                <p className="text-xs text-slate-500">{entity.description}</p>
                <FieldTable title="" fields={entity.fields} />
              </div>
            ))}
          </div>

          <p className="mt-4 text-xs font-medium uppercase tracking-wide text-slate-400">Notes</p>
          <p className="mt-1 whitespace-pre-wrap text-xs text-slate-600">
            {service.internal_logic_notes}
          </p>
        </div>
      ))}
    </div>
  )
}
