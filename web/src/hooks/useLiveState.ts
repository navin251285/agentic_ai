import { useEffect } from 'react'

import type { Snapshot } from '../api/client'
import { useShopStore } from '../store/useShopStore'

export const STREAM_URL = '/api/stream'
/** EventSource retries by itself after a dropped connection, but gives up for good when the
 * server answers with an error (e.g. the dev proxy's 502 while the api restarts). Then we
 * open a new one after this delay. */
export const RECONNECT_MS = 2000

/** Feeds the store from the SSE stream: every message is a full Snapshot. */
export function useLiveState(url: string = STREAM_URL): void {
  useEffect(() => {
    const { setSnapshot, setConnection } = useShopStore.getState()
    let source: EventSource | null = null
    let retry: ReturnType<typeof setTimeout> | undefined

    const connect = () => {
      source = new EventSource(url)
      source.onopen = () => setConnection('open')
      source.onmessage = (event: MessageEvent<string>) => {
        try {
          setSnapshot(JSON.parse(event.data) as Snapshot)
        } catch {
          // A malformed frame is skipped; the next tick brings a full snapshot again.
        }
      }
      source.onerror = () => {
        setConnection('reconnecting')
        if (source?.readyState === EventSource.CLOSED) {
          source.close()
          retry = setTimeout(connect, RECONNECT_MS)
        }
      }
    }

    connect()
    return () => {
      clearTimeout(retry)
      source?.close()
    }
  }, [url])
}
