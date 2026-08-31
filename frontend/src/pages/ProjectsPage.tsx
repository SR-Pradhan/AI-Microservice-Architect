import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type Project } from '../lib/api'

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([])
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
      setError(String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mx-auto max-w-3xl p-8">
      <h1 className="text-2xl font-semibold text-slate-900">AI Microservice Architect</h1>
      <p className="mt-1 text-sm text-slate-500">
        Describe a system in plain English, then walk it through six review stages.
      </p>

      <form onSubmit={handleCreate} className="mt-8 space-y-3 rounded-lg border border-slate-200 p-5">
        <input
          className="w-full rounded border border-slate-300 px-3 py-2 text-sm"
          placeholder="Project name (e.g. Flipkart-like e-commerce)"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />
        <textarea
          className="h-32 w-full rounded border border-slate-300 px-3 py-2 text-sm"
          placeholder="Describe the system, its users, and any constraints..."
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          required
          minLength={10}
        />
        <button
          type="submit"
          disabled={busy}
          className="rounded bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {busy ? 'Creating...' : 'Create project'}
        </button>
      </form>

      {error && <p className="mt-4 text-sm text-red-600">{error}</p>}

      <ul className="mt-8 divide-y divide-slate-200 rounded-lg border border-slate-200">
        {projects.length === 0 && (
          <li className="p-4 text-sm text-slate-500">No projects yet.</li>
        )}
        {projects.map((p) => (
          <li key={p.id} className="p-4">
            <Link to={`/projects/${p.id}`} className="font-medium text-slate-900 hover:underline">
              {p.name}
            </Link>
            <p className="mt-1 line-clamp-2 text-sm text-slate-500">{p.raw_description}</p>
          </li>
        ))}
      </ul>
    </div>
  )
}
