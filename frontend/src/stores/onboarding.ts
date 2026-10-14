import { create } from 'zustand'
import { persist } from 'zustand/middleware'

type OnboardingState = {
  /** Shops whose owner finished (or skipped) the setup wizard on this browser. */
  done: string[]
  markDone: (shopId: string) => void
}

export const useOnboardingStore = create<OnboardingState>()(
  persist(
    (set) => ({
      done: [],
      markDone: (shopId) => set((s) => (s.done.includes(shopId) ? s : { done: [...s.done, shopId] })),
    }),
    { name: 'codguard-onboarding' },
  ),
)
