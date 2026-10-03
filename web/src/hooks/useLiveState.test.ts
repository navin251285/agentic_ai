import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { Snapshot } from '../api/client'
import { useShopStore } from '../store/useShopStore'
import { RECONNECT_MS, useLiveState } from './useLiveState'

class FakeEventSource {
  static readonly CONNECTING = 0
  static readonly OPEN = 1
  static readonly CLOSED = 2
  static instances: FakeEventSource[] = []

  readyState = FakeEventSource.CONNECTING
  onopen: (() => void) | null = null
  onmessage: ((event: MessageEvent<string>) => void) | null = null
  onerror: (() => void) | null = null
  readonly url: string

  constructor(url: string) {
    this.url = url
    FakeEventSource.instances.push(this)
  }

  open() {
    this.readyState = FakeEventSource.OPEN
    this.onopen?.()
  }

  send(data: string) {
    this.onmessage?.({ data } as MessageEvent<string>)
  }

  fail(readyState: number) {
    this.readyState = readyState
    this.onerror?.()
  }

  close() {
    this.readyState = FakeEventSource.CLOSED
  }
}

const latest = () => FakeEventSource.instances.at(-1)!
const frame = (sim_s: number) => JSON.stringify({ sim_s, products: [] })

describe('useLiveState', () => {
  beforeEach(() => {
    FakeEventSource.instances = []
    vi.stubGlobal('EventSource', FakeEventSource)
    vi.useFakeTimers()
    useShopStore.setState({ snapshot: null, connection: 'connecting' })
  })
  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('puts every message into the store', () => {
    renderHook(() => useLiveState())
    expect(latest().url).toBe('/api/stream')
    act(() => latest().open())
    expect(useShopStore.getState().connection).toBe('open')
    act(() => latest().send(frame(1.5)))
    act(() => latest().send(frame(2)))
    expect((useShopStore.getState().snapshot as Snapshot).sim_s).toBe(2)
  })

  it('skips a malformed frame and keeps the last snapshot', () => {
    renderHook(() => useLiveState())
    act(() => latest().send(frame(3)))
    act(() => latest().send('{not json'))
    expect(useShopStore.getState().snapshot?.sim_s).toBe(3)
  })

  it('shows reconnecting while EventSource retries by itself', () => {
    renderHook(() => useLiveState())
    act(() => latest().fail(FakeEventSource.CONNECTING))
    expect(useShopStore.getState().connection).toBe('reconnecting')
    act(() => vi.advanceTimersByTime(RECONNECT_MS * 2))
    expect(FakeEventSource.instances).toHaveLength(1) // the browser retries; no new source
    act(() => latest().open())
    expect(useShopStore.getState().connection).toBe('open')
  })

  it('opens a new EventSource when the old one gave up', () => {
    renderHook(() => useLiveState())
    act(() => latest().fail(FakeEventSource.CLOSED))
    act(() => vi.advanceTimersByTime(RECONNECT_MS - 1))
    expect(FakeEventSource.instances).toHaveLength(1)
    act(() => vi.advanceTimersByTime(1))
    expect(FakeEventSource.instances).toHaveLength(2)
  })

  it('closes the stream and cancels a pending reconnect on unmount', () => {
    const { unmount } = renderHook(() => useLiveState())
    const first = latest()
    act(() => first.fail(FakeEventSource.CLOSED))
    unmount()
    act(() => vi.advanceTimersByTime(RECONNECT_MS * 2))
    expect(FakeEventSource.instances).toHaveLength(1)
    expect(first.readyState).toBe(FakeEventSource.CLOSED)
  })
})
