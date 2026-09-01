import { useCallback, useEffect, useRef, useState } from 'react'
import mermaid from 'mermaid'
import { useTheme, type ResolvedTheme } from '../lib/theme'

// Mermaid bakes colours into the SVG it produces, so it must be re-initialised and the diagram
// re-rendered whenever the theme changes — otherwise a light diagram sits on a dark page.
//
// useMaxWidth:false stops Mermaid shrinking the SVG to fit its container — a 13-table ER diagram
// scaled to fit is unreadable. Default ER layout is top-down, which stacks many tables into a tall
// sparse column, so LR spreads them across the width instead.
function configure(theme: ResolvedTheme) {
  mermaid.initialize({
    startOnLoad: false,
    theme: theme === 'dark' ? 'dark' : 'neutral',
    darkMode: theme === 'dark',
    securityLevel: 'strict',
    flowchart: { useMaxWidth: false },
    er: { useMaxWidth: false, layoutDirection: 'LR' },
  })
}

let renderCount = 0

const ZOOM_STEP = 0.25
const MIN_ZOOM = 0.25
const MAX_ZOOM = 3

interface Size {
  width: number
  height: number
}

export default function MermaidDiagram({ code }: { code: string }) {
  const container = useRef<HTMLDivElement>(null)
  const [error, setError] = useState<string | null>(null)
  const [natural, setNatural] = useState<Size | null>(null)
  const [zoom, setZoom] = useState(1)
  const { resolved } = useTheme()

  useEffect(() => {
    configure(resolved)
    // Renders are async, so a fast re-render could otherwise paint an older diagram last.
    let cancelled = false
    const id = `mermaid-${renderCount++}`

    mermaid
      .render(id, code)
      .then(({ svg }) => {
        if (cancelled || !container.current) return
        container.current.innerHTML = svg
        const el = container.current.querySelector('svg')
        if (!el) return

        // The viewBox carries the diagram's true size; width/height attributes may not.
        const [, , vbWidth, vbHeight] = (el.getAttribute('viewBox') ?? '0 0 0 0')
          .split(/\s+/)
          .map(Number)
        const size = {
          width: vbWidth || el.clientWidth,
          height: vbHeight || el.clientHeight,
        }
        setNatural(size)

        // Start at whatever zoom makes the whole diagram fit the panel width, never above 100%.
        const available = container.current.parentElement?.clientWidth ?? size.width
        const fit = size.width > 0 ? available / size.width : 1
        setZoom(Math.max(MIN_ZOOM, Math.min(1, Number(fit.toFixed(2)))))
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
  }, [code, resolved])

  // Resize the SVG itself rather than CSS-transforming it: a transform scales what you see but not
  // the space the element reserves, which leaves a large blank gap when zoomed out.
  useEffect(() => {
    const el = container.current?.querySelector('svg')
    if (!el || !natural) return
    el.style.width = `${natural.width * zoom}px`
    el.style.height = `${natural.height * zoom}px`
    el.style.maxWidth = 'none'
  }, [zoom, natural])

  const adjust = useCallback(
    (delta: number) => setZoom((z) => Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, z + delta))),
    [],
  )

  if (error) {
    return (
      <div className="rounded border border-red-200 bg-red-50 p-3 dark:border-red-900 dark:bg-red-950/60">
        <p className="text-xs font-medium text-red-800 dark:text-red-200">Could not draw the diagram</p>
        <pre className="mt-1 overflow-x-auto text-xs text-red-600 dark:text-red-300">{error}</pre>
      </div>
    )
  }

  return (
    <div className="rounded border border-line bg-surface">
      <div className="flex items-center gap-1 border-b border-line px-2 py-1">
        <button
          onClick={() => adjust(-ZOOM_STEP)}
          disabled={zoom <= MIN_ZOOM}
          aria-label="Zoom out"
          className="rounded px-2 py-0.5 text-sm text-ink-muted hover:bg-canvas disabled:opacity-30"
        >
          −
        </button>
        <span className="w-12 text-center text-xs tabular-nums text-ink-muted">
          {Math.round(zoom * 100)}%
        </span>
        <button
          onClick={() => adjust(ZOOM_STEP)}
          disabled={zoom >= MAX_ZOOM}
          aria-label="Zoom in"
          className="rounded px-2 py-0.5 text-sm text-ink-muted hover:bg-canvas disabled:opacity-30"
        >
          +
        </button>
        <button
          onClick={() => setZoom(1)}
          className="ml-1 rounded px-2 py-0.5 text-xs text-ink-muted hover:bg-canvas"
        >
          100%
        </button>
        <span className="ml-auto text-xs text-ink-faint">scroll to pan</span>
      </div>
      {/* max-h, not h: the panel shrinks to the diagram when the diagram is small. */}
      <div className="max-h-[80vh] overflow-auto p-3">
        <div ref={container} />
      </div>
    </div>
  )
}
