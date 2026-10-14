import { useAuthStore } from '@/stores/auth'

export class SignInError extends Error {}

/**
 * Signs the shop user in and stores their bearer token.
 *
 * Firebase Auth is not wired yet (E7.1). Until then this only works in local development: with
 * VITE_DEV_AUTH_TOKEN set it accepts any credentials and stores that token, which the Prism mock
 * accepts. Replace the body with Firebase `signInWithEmailAndPassword`.
 */
export async function signIn(_credentials: { email: string; password: string }): Promise<void> {
  const devToken = import.meta.env.VITE_DEV_AUTH_TOKEN
  if (!devToken) {
    throw new SignInError('Đăng nhập chưa được cấu hình (cần Firebase Auth, E7.1).')
  }
  useAuthStore.getState().setToken(devToken)
}

export function signOut(): void {
  useAuthStore.getState().signOut()
}

/** Where to go after signing in: only paths inside the app, never an absolute or protocol-relative URL. */
export function safeRedirect(target: string | undefined): string {
  return target?.startsWith('/') && !target.startsWith('//') && !target.startsWith('/\\') ? target : '/'
}
