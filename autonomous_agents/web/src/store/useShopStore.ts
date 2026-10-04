import { create } from 'zustand'

import type { Snapshot } from '../api/client'

export type Connection = 'connecting' | 'open' | 'reconnecting'

interface ShopState {
  /** Latest snapshot from the server; null until the first one arrives. */
  snapshot: Snapshot | null
  connection: Connection
  /** Last failed action, shown by the ConnectionBanner until dismissed or the next success. */
  actionError: string | null
  setSnapshot: (snapshot: Snapshot) => void
  setConnection: (connection: Connection) => void
  setActionError: (message: string | null) => void
}

export const useShopStore = create<ShopState>()((set) => ({
  snapshot: null,
  connection: 'connecting',
  actionError: null,
  setSnapshot: (snapshot) => set({ snapshot }),
  setConnection: (connection) => set({ connection }),
  setActionError: (actionError) => set({ actionError }),
}))

/** Runs an action that answers with a fresh Snapshot and shows it at once (before the next SSE tick).
 * Errors are re-thrown; with `banner` false the caller shows them itself (e.g. inline in the edit form). */
export async function runAction(action: Promise<Snapshot>, banner = true): Promise<Snapshot> {
  const { setSnapshot, setActionError } = useShopStore.getState()
  try {
    const snapshot = await action
    setSnapshot(snapshot)
    setActionError(null)
    return snapshot
  } catch (err) {
    if (banner) setActionError(err instanceof Error ? err.message : String(err))
    throw err
  }
}

/** Fire-and-forget variant for buttons: the banner already shows the error. */
export function act(action: Promise<Snapshot>): void {
  runAction(action).catch(() => {})
}
