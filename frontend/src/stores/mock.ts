import { create } from 'zustand'

type MockState = {
  /** Endpoints answered by the in-browser mock in this session, e.g. "GET /api/v1/shop". */
  mocked: string[]
  record: (operation: string) => void
}

export const useMockStore = create<MockState>()((set) => ({
  mocked: [],
  record: (operation) =>
    set((state) => (state.mocked.includes(operation) ? state : { mocked: [...state.mocked, operation] })),
}))
