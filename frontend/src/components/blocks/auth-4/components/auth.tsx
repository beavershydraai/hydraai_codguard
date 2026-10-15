import { AlertCircleIcon, EyeIcon, EyeOffIcon } from 'lucide-react'
import * as React from 'react'

import { Frame, FrameDescription, FramePanel, FrameTitle } from '@/components/ui/frame'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Field, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { InputGroup, InputGroupAddon, InputGroupButton, InputGroupInput } from '@/components/ui/input-group'
import { Spinner } from '@/components/ui/spinner'
import { signIn, SignInError } from '@/lib/auth'

import { AuthLogo } from './auth-logo'

type FormSubmitHandler = NonNullable<React.ComponentProps<'form'>['onSubmit']>
type FormSubmitEvent = Parameters<FormSubmitHandler>[0]

export function Auth({ onSignedIn }: { onSignedIn: () => void }) {
  const [showPassword, setShowPassword] = React.useState(false)
  const [pending, setPending] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)

  async function run(credentials: { email: string; password: string }) {
    setPending(true)
    setError(null)
    try {
      await signIn(credentials)
      onSignedIn()
    } catch (err) {
      setError(err instanceof SignInError ? err.message : 'Could not sign in. Please try again.')
    } finally {
      setPending(false)
    }
  }

  function handleSubmit(event: FormSubmitEvent) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    void run({ email: String(form.get('email')), password: String(form.get('password')) })
  }

  return (
    <div className="relative flex min-h-svh w-full min-w-full flex-col">
      <div className="flex w-full min-w-full flex-1 items-center justify-center px-4 py-8 sm:px-6 sm:py-10 lg:px-10">
        <div className="mx-auto flex w-full max-w-[28rem] flex-col gap-4">
          <Frame spacing="lg" className="w-full">
            <FramePanel className="space-y-8 px-9 py-10 sm:space-y-9 sm:px-11 sm:py-11">
              <div className="flex flex-col items-center gap-5 pt-3 text-center">
                <AuthLogo className="size-9" />

                <div className="flex max-w-xs flex-col gap-1.5">
                  <FrameTitle className="text-2xl tracking-tight sm:text-[1.75rem]">Sign in</FrameTitle>
                  <FrameDescription className="text-sm text-pretty">
                    Sign in to COD Guard to screen your shop's COD orders.
                  </FrameDescription>
                </div>
              </div>

              <form className="flex flex-col gap-5" onSubmit={handleSubmit}>
                <FieldGroup className="gap-4">
                  <Field className="gap-2">
                    <FieldLabel htmlFor="login-email">Email</FieldLabel>
                    <Input
                      id="login-email"
                      name="email"
                      type="email"
                      autoComplete="username"
                      placeholder="you@shop.vn"
                      required
                    />
                  </Field>

                  <Field className="gap-2">
                    <FieldLabel htmlFor="login-password">Password</FieldLabel>

                    <InputGroup className="w-full">
                      <InputGroupInput
                        id="login-password"
                        name="password"
                        type={showPassword ? 'text' : 'password'}
                        autoComplete="current-password"
                        placeholder="Enter your password"
                        required
                      />
                      <InputGroupAddon align="inline-end">
                        <InputGroupButton
                          type="button"
                          size="icon-xs"
                          className="text-muted-foreground hover:text-foreground"
                          aria-label={showPassword ? 'Hide password' : 'Show password'}
                          aria-pressed={showPassword}
                          onClick={() => setShowPassword((value) => !value)}
                        >
                          {showPassword ? (
                            <EyeOffIcon aria-hidden="true" className="size-4" />
                          ) : (
                            <EyeIcon aria-hidden="true" className="size-4" />
                          )}
                        </InputGroupButton>
                      </InputGroupAddon>
                    </InputGroup>
                  </Field>
                </FieldGroup>

                {error && (
                  <Alert variant="destructive" role="alert">
                    <AlertCircleIcon />
                    <AlertDescription>{error}</AlertDescription>
                  </Alert>
                )}

                <Button type="submit" className="w-full" disabled={pending}>
                  {pending && <Spinner data-icon="inline-start" />}
                  Sign in
                </Button>
              </form>
            </FramePanel>
          </Frame>
        </div>
      </div>
    </div>
  )
}
