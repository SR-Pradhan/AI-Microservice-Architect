import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type Project } from '../lib/api'
import AppShell from '../components/AppShell'
import { Alert, Button, Card, Field, Skeleton, inputClass } from '../components/ui'

const EXAMPLE =
  'An online marketplace where sellers list products and customers browse a catalog, search, add ' +
  'items to a cart, place orders, pay by card or UPI, and track shipping. Includes inventory ' +
  'management, order notifications, product reviews, and seller payouts.'

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
      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_380px]">
        <section className="order-2 lg:order-1">
          <h2 className="text-sm font-medium uppercase tracking-wide text-ink-faint">Projects</h2>

          {projects === null && (
            <div className="mt-3 space-y-3">
              {[0, 1, 2].map((i) => (
                <Card key={i} className="p-4">
                  <Skeleton className="h-4 w-48" />
                  <Skeleton className="mt-2.5 h-3 w-full" />
                  <Skeleton className="mt-1.5 h-3 w-2/3" />
                </Card>
              ))}
            </div>
          )}

          {projects?.length === 0 && (
            <Card className="mt-3 px-6 py-12 text-center">
              <p className="text-sm font-medium text-ink">No projects yet</p>
              <p className="mx-auto mt-1 max-w-sm text-sm text-ink-muted">
                Describe a system on the right and the pipeline will design it stage by stage.
              </p>
            </Card>
          )}

          <div className="mt-3 space-y-3">
            {projects?.map((project) => (
              <Card key={project.id} className="group transition-colors hover:border-line-strong">
                <div className="flex items-start justify-between gap-3 p-4">
                  <div className="min-w-0">
                    <Link
                      to={`/projects/${project.id}`}
                      className="text-sm font-semibold text-ink hover:text-accent"
                    >
                      {project.name}
                    </Link>
                    <p className="mt-1 line-clamp-2 text-sm text-ink-muted">
                      {project.raw_description}
                    </p>
                    <p className="mt-2 text-xs text-ink-faint">
                      Created {new Date(project.created_at).toLocaleDateString()}
                    </p>
                  </div>
                  <Button
                    variant="danger"
                    size="sm"
                    onClick={() => handleDelete(project)}
                    aria-label={`Delete ${project.name}`}
                    className="shrink-0 opacity-0 focus:opacity-100 group-hover:opacity-100"
                  >
                    Delete
                  </Button>
                </div>
              </Card>
            ))}
          </div>
        </section>

        <section className="order-1 lg:order-2">
          <Card className="p-5 lg:sticky lg:top-20">
            <h2 className="text-sm font-semibold text-ink">New project</h2>
            <p className="mt-1 text-xs text-ink-muted">
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
