import { useTheme, type ThemeChoice } from '../lib/theme'

const OPTIONS: { value: ThemeChoice; label: string; glyph: string }[] = [
  { value: 'light', label: 'Light', glyph: '☀' },
  { value: 'system', label: 'System', glyph: '◐' },
  { value: 'dark', label: 'Dark', glyph: '☾' },
]

export default function ThemeToggle() {
  const { choice, setChoice } = useTheme()

  return (
    <div
      role="radiogroup"
      aria-label="Colour theme"
      className="inline-flex rounded-md border border-line bg-canvas p-0.5"
    >
      {OPTIONS.map((option) => (
        <button
          key={option.value}
          role="radio"
          aria-checked={choice === option.value}
          aria-label={option.label}
          title={option.label}
          onClick={() => setChoice(option.value)}
          className={`rounded px-2 py-1 text-xs transition-colors ${
            choice === option.value
              ? 'bg-surface text-ink shadow-sm'
              : 'text-ink-faint hover:text-ink-muted'
          }`}
        >
          <span aria-hidden>{option.glyph}</span>
        </button>
      ))}
    </div>
  )
}
