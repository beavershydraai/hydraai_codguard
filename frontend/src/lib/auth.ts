import { login } from '@/api/gen'
import { useAuthStore } from '@/stores/auth'

export class SignInError extends Error {}

/**
 * Signs the shop user in with `POST /api/v1/auth/login` and stores the returned bearer token.
 * The Prism mock answers with its example token for any credentials.
 */
export async function signIn({ email, password }: { email: string; password: string }): Promise<void> {
  let result
  try {
    result = await login({ body: { username: email, password } })
  } catch {
    throw new SignInError('Could not reach the server. Please try again.')
  }
  if (result.data) {
    useAuthStore.getState().setToken(result.data.access_token)
    return
  }
  const status = result.response?.status
  if (status === 401 || status === 422) {
    throw new SignInError('Wrong email or password.')
  }
  throw new SignInError('Could not sign in. Please try again.')
}

export function signOut(): void {
  useAuthStore.getState().signOut()
}

/** Where to go after signing in: only paths inside the app, never an absolute or protocol-relative URL. */
export function safeRedirect(target: string | undefined): string {
  return target?.startsWith('/') && !target.startsWith('//') && !target.startsWith('/\\') ? target : '/'
}
