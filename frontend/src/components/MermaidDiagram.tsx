import { useEffect, useRef, useState } from 'react'
import mermaid from 'mermaid'

mermaid.initialize({ startOnLoad: false, theme: 'neutral', securityLevel: 'strict' })

let renderCount = 0

export default function MermaidDiagram({ code }: { code: string }) {
  const container = useRef<HTMLDivElement>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    // Renders are async, so a fast re-render could otherwise paint an older diagram last.
    let cancelled = false
    const id = `mermaid-${renderCount++}`

    mermaid
      .render(id, code)
      .then(({ svg }) => {
        if (cancelled || !container.current) return
        container.current.innerHTML = svg
        setError(null)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setError(err instanceof Error ? err.message : String(err))
      })

    return () => {
      cancelled = true
      // Mermaid appends a hidden measuring node to <body> per render; drop it so they don't pile up.
      document.getElementById(`d${id}`)?.remove()
    }
  }, [code])

  if (error) {
    return (
      <div className="rounded border border-red-200 bg-red-50 p-3">
        <p className="text-xs font-medium text-red-700">Could not draw the diagram</p>
        <pre className="mt-1 overflow-x-auto text-xs text-red-600">{error}</pre>
      </div>
    )
  }

  return (
    <div className="overflow-x-auto rounded border border-slate-200 bg-white p-3">
      <div ref={container} />
    </div>
  )
}
