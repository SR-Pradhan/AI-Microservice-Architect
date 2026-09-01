/** Theme state: an explicit light/dark choice, or "system" which follows the OS.
 *
 *  The choice lives on <html data-theme>, which the CSS tokens key off. Nothing else in the app
 *  needs to know which theme is active — components only ever use the tokens.
 */

import { useEffect, useState } from 'react'

export type ThemeChoice = 'light' | 'dark' | 'system'
export type ResolvedTheme = 'light' | 'dark'

const STORAGE_KEY = 'ama-theme'

export function readStoredChoice(): ThemeChoice {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === 'light' || stored === 'dark' || stored === 'system') return stored
  } catch {
    /* private mode or blocked storage — fall through to the default */
  }
  return 'system'
}

function systemTheme(): ResolvedTheme {
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export function applyChoice(choice: ThemeChoice): void {
  // The attribute always holds a concrete theme, even for "system" — so CSS never has to duplicate
  // every rule across a media query and an attribute selector.
  document.documentElement.setAttribute(
    'data-theme',
    choice === 'system' ? systemTheme() : choice,
  )
  try {
    localStorage.setItem(STORAGE_KEY, choice)
  } catch {
    /* storing the preference is a convenience, never a requirement */
  }
}

export function useTheme() {
  const [choice, setChoice] = useState<ThemeChoice>(readStoredChoice)
  const [resolved, setResolved] = useState<ResolvedTheme>(() =>
    readStoredChoice() === 'system' ? systemTheme() : (readStoredChoice() as ResolvedTheme),
  )

  useEffect(() => {
    applyChoice(choice)
    setResolved(choice === 'system' ? systemTheme() : choice)

    if (choice !== 'system') return
    // Only follow the OS while the user has not made an explicit choice.
    const media = window.matchMedia('(prefers-color-scheme: dark)')
    const onChange = () => setResolved(systemTheme())
    media.addEventListener('change', onChange)
    return () => media.removeEventListener('change', onChange)
  }, [choice])

  return { choice, resolved, setChoice }
}
