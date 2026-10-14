import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type Theme = 'light' | 'dark' | 'system'

type ThemeState = {
  theme: Theme
  setTheme: (theme: Theme) => void
}

export const useThemeStore = create<ThemeState>()(
  persist(
    (set) => ({
      theme: 'system',
      setTheme: (theme) => set({ theme }),
    }),
    { name: 'codguard-theme' },
  ),
)

const darkQuery = window.matchMedia('(prefers-color-scheme: dark)')

function applyTheme(theme: Theme) {
  const dark = theme === 'dark' || (theme === 'system' && darkQuery.matches)
  document.documentElement.classList.toggle('dark', dark)
  document.documentElement.style.colorScheme = dark ? 'dark' : 'light'
}

/** Keeps the `dark` class on <html> in sync with the chosen theme and, for "system", the OS. */
export function syncThemeWithDocument() {
  applyTheme(useThemeStore.getState().theme)
  useThemeStore.subscribe((state) => applyTheme(state.theme))
  darkQuery.addEventListener('change', () => applyTheme(useThemeStore.getState().theme))
}
