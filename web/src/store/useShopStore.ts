import { create } from 'zustand'

import type { Snapshot } from '../api/client'

export type Connection = 'connecting' | 'open' | 'reconnecting'

interface ShopState {
  /** Latest snapshot from the server; null until the first one arrives. */
  snapshot: Snapshot | null
  connection: Connection
  setSnapshot: (snapshot: Snapshot) => void
  setConnection: (connection: Connection) => void
}

export const useShopStore = create<ShopState>()((set) => ({
  snapshot: null,
  connection: 'connecting',
  setSnapshot: (snapshot) => set({ snapshot }),
  setConnection: (connection) => set({ connection }),
}))
