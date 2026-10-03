import { useEffect, useState } from 'react'

import { api, type History } from '../api/client'

/** Loads GET /api/history/{id} and reloads it whenever `refreshKey` changes (e.g. the product's latest
 * event in the live snapshot) or a new run starts. Responses that arrive out of order are dropped. */
export function useStockHistory(productId: string, runId: number, refreshKey: string): History | null {
  const [loaded, setLoaded] = useState<{ runId: number; history: History } | null>(null)

  useEffect(() => {
    let stale = false
    api
      .history(productId)
      .then((history) => !stale && setLoaded({ runId, history }))
      .catch(() => {
        // Keep the last chart; the next snapshot change triggers another try.
      })
    return () => {
      stale = true
    }
  }, [productId, runId, refreshKey])

  // Another product's or an earlier run's history is never shown while the reload is in flight.
  return loaded && loaded.runId === runId && loaded.history.product_id === productId ? loaded.history : null
}
