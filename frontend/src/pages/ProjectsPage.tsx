import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type Project } from '../lib/api'
import AppShell from '../components/AppShell'
import StageDots from '../components/StageDots'
import { Alert, Button, Card, Field, Skeleton, inputClass } from '../components/ui'

const EXAMPLE =
  'An online marketplace where sellers list products and customers browse a catalog, search, add ' +
  'items to a cart, place orders, pay by card or UPI, and track shipping. Includes inventory ' +
  'management, order notifications, product reviews, and seller payouts.'

const STEPS = ['Boundaries', 'HLD', 'LLD', 'Schemas', 'Events', 'Infra']

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[] | null>(null)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const load = () => api.listProjects().then(setProjects).catch((e) => setError(String(e)))

  useEffect(() => {
    load()
  }, [])

  const stats = useMemo(() => {
    if (!projects) return null
    const complete = projects.filter((p) => p.stage_statuses.every((s) => s === 'approved')).length
    const inProgress = projects.filter(
      (p) => p.stage_statuses.some((s) => s !== 'pending') && !p.stage_statuses.every((s) => s === 'approved'),
    ).length
    return { total: projects.length, complete, inProgress }
  }, [projects])

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await api.createProject(name, description)
      setName('')
      setDescription('')
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  async function handleDelete(project: Project) {
    // Deleting a project cascades to its six stages, so make the user confirm it deliberately.
    if (!confirm(`Delete "${project.name}" and all its generated stages? This cannot be undone.`))
      return
    setError(null)
    try {
      await api.deleteProject(project.id)
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  return (
    <AppShell>
      <section className="bg-grid -mx-6 -mt-8 border-b border-line px-6 pb-10 pt-14">
        <div>
          <h1 className="max-w-3xl text-4xl font-semibold leading-tight tracking-tight text-ink">
            Describe a system.
            <br />
            <span className="text-ink-muted">Get an architecture you can actually ship.</span>
          </h1>
          <p className="mt-4 max-w-2xl text-sm leading-relaxed text-ink-muted">
            Six stages, each one reviewed and approved by you before the next runs — boundaries,
            high-level design, contracts, schemas, event topics, and deployment manifests. Every
            stage is validated against the ones before it.
          </p>

          <ol className="mt-6 flex flex-wrap items-center gap-x-2 gap-y-2 text-xs">
            {STEPS.map((step, i) => (
              <li key={step} className="flex items-center gap-2">
                <span className="rounded-full border border-line bg-surface px-2.5 py-1 font-medium text-ink-muted">
                  <span className="text-ink-faint">{i + 1}</span> {step}
                </span>
                {i < STEPS.length - 1 && <span aria-hidden className="text-ink-faint">→</span>}
              </li>
            ))}
          </ol>

          {stats && stats.total > 0 && (
            <p className="mt-6 text-xs text-ink-faint">
              <span className="font-medium text-ink-muted">{stats.total}</span> project
              {stats.total === 1 ? '' : 's'} ·{' '}
              <span className="font-medium text-ink-muted">{stats.complete}</span> complete ·{' '}
              <span className="font-medium text-ink-muted">{stats.inProgress}</span> in progress
            </p>
          )}
        </div>
      </section>

      <div className="mt-8 grid gap-8 lg:grid-cols-[minmax(0,1fr)_360px]">
        <section className="order-2 lg:order-1">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-ink-faint">Projects</h2>

          {projects === null && (
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              {[0, 1, 2, 3].map((i) => (
                <Card key={i} className="p-4">
                  <Skeleton className="h-4 w-40" />
                  <Skeleton className="mt-2.5 h-3 w-full" />
                  <Skeleton className="mt-1.5 h-3 w-2/3" />
                  <Skeleton className="mt-4 h-1.5 w-40" />
                </Card>
              ))}
            </div>
          )}

          {projects?.length === 0 && (
            <Card className="mt-3 px-6 py-14 text-center">
              <p className="text-sm font-medium text-ink">No projects yet</p>
              <p className="mx-auto mt-1 max-w-sm text-sm text-ink-muted">
                Describe a system on the right, or start from the example.
              </p>
            </Card>
          )}

          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            {projects?.map((project) => {
              const complete = project.stage_statuses.every((s) => s === 'approved')
              return (
                <Card
                  key={project.id}
                  className="group relative flex flex-col transition-all hover:border-accent/40 hover:shadow-sm"
                >
                  <Link to={`/projects/${project.id}`} className="flex-1 p-4">
                    <span className="absolute inset-0" aria-hidden />
                    <div className="flex items-start gap-2">
                      <h3 className="min-w-0 flex-1 truncate text-sm font-semibold text-ink group-hover:text-accent">
                        {project.name}
                      </h3>
                      {complete && (
                        <span className="shrink-0 rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300">
                          Complete
                        </span>
                      )}
                    </div>
                    <p className="mt-1.5 line-clamp-2 text-sm leading-relaxed text-ink-muted">
                      {project.raw_description}
                    </p>
                  </Link>
                  <div className="flex items-center justify-between gap-2 border-t border-line px-4 py-2.5">
                    <StageDots statuses={project.stage_statuses} />
                    <button
                      onClick={() => handleDelete(project)}
                      aria-label={`Delete ${project.name}`}
                      className="relative z-10 rounded px-2 py-1 text-xs text-ink-faint opacity-0 transition hover:bg-red-50 hover:text-red-600 focus:opacity-100 group-hover:opacity-100 dark:hover:bg-red-950 dark:hover:text-red-300"
                    >
                      Delete
                    </button>
                  </div>
                </Card>
              )
            })}
          </div>
        </section>

        <section className="order-1 lg:order-2">
          <Card className="p-5 lg:sticky lg:top-20">
            <h2 className="text-sm font-semibold text-ink">New project</h2>
            <p className="mt-1 text-xs leading-relaxed text-ink-muted">
              The more concrete the description, the better the architecture. Name the actors, the
              flows and the constraints.
            </p>

            <form onSubmit={handleCreate} className="mt-4 space-y-4">
              <Field label="Name">
                <input
                  className={inputClass}
                  placeholder="Flipkart-like e-commerce"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                />
              </Field>

              <Field label="System description" hint="min 10 characters">
                <textarea
                  className={`${inputClass} h-40 resize-y leading-relaxed`}
                  placeholder="Describe the system, its users, and any constraints…"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  required
                  minLength={10}
                />
              </Field>

              <div className="flex items-center gap-2">
                <Button type="submit" variant="primary" disabled={busy}>
                  {busy ? 'Creating…' : 'Create project'}
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setName('Flipkart-like e-commerce')
                    setDescription(EXAMPLE)
                  }}
                >
                  Use an example
                </Button>
              </div>

              {error && <Alert onDismiss={() => setError(null)}>{error}</Alert>}
            </form>
          </Card>
        </section>
      </div>
    </AppShell>
  )
}
