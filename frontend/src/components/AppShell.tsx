import { Link } from 'react-router-dom'
import type { ReactNode } from 'react'
import ThemeToggle from './ThemeToggle'

/** Header + page frame. Gives every route the same width, padding and identity. */
export default function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-canvas">
      <header className="sticky top-0 z-20 border-b border-line bg-surface/85 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-7xl items-center gap-3 px-6">
          <Link to="/" className="flex items-center gap-2.5">
            <span
              aria-hidden
              className="grid h-7 w-7 place-items-center rounded-md bg-accent text-[13px] font-bold text-white"
            >
              A
            </span>
            <span className="text-sm font-semibold tracking-tight text-ink">
              AI Microservice Architect
            </span>
          </Link>
          <span className="hidden text-xs text-ink-faint sm:inline">
            plain English → reviewed architecture
          </span>
          <div className="ml-auto">
            <ThemeToggle />
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-6 py-8">{children}</main>
    </div>
  )
}
