import { create } from 'zustand'

type AuthState = {
  /** Firebase ID token sent as `Authorization: Bearer`. */
  token: string | null
  setToken: (token: string | null) => void
}

// Firebase Auth is not wired yet (E7.1). Until then a token from VITE_DEV_AUTH_TOKEN lets the
// app talk to the Prism mock, which accepts any bearer token.
export const useAuthStore = create<AuthState>()((set) => ({
  token: import.meta.env.VITE_DEV_AUTH_TOKEN || null,
  setToken: (token) => set({ token }),
}))
