import { Toaster as Sonner } from 'sonner'

import { useThemeStore } from '@/stores/theme'

/** Toasts (sonner), following the theme chosen in the user menu. */
export function Toaster() {
  const theme = useThemeStore((state) => state.theme)
  return <Sonner theme={theme} position="bottom-right" richColors closeButton />
}
