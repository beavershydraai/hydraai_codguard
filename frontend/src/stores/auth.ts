import { create } from 'zustand'
import { persist } from 'zustand/middleware'

type AuthState = {
  /** Firebase ID token sent as `Authorization: Bearer`. */
  token: string | null
  setToken: (token: string) => void
  signOut: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      setToken: (token) => set({ token }),
      signOut: () => set({ token: null }),
    }),
    { name: 'codguard-auth' },
  ),
)
