import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { api, type History } from '../api/client'
import { makeEvent, makeSnapshot } from '../test/fixtures'
import { StockChart } from './StockChart'

const empty = (product_id: string): History => ({ product_id, window_s: 600, points: [], markers: [], shadow_points: [] })

describe('StockChart', () => {
  let history: ReturnType<typeof vi.spyOn>
  beforeEach(() => {
    history = vi.spyOn(api, 'history').mockImplementation(async (id) => empty(id))
  })
  afterEach(() => vi.restoreAllMocks())

  it('charts the first product and switches with the chips', async () => {
    render(<StockChart snapshot={makeSnapshot()} />)
    expect(screen.getByRole('heading', { name: 'Milk · stock over time' })).toBeInTheDocument()
    expect(history).toHaveBeenCalledWith('milk')
    fireEvent.click(screen.getByRole('button', { name: 'Eggs' }))
    expect(screen.getByRole('heading', { name: 'Eggs · stock over time' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Eggs' })).toHaveAttribute('aria-pressed', 'true')
    await vi.waitFor(() => expect(history).toHaveBeenLastCalledWith('eggs'))
  })

  it("reloads on a new event for the product or a new run, not on other products' events", async () => {
    const milkEvent = makeEvent({ type: 'SALE' })
    const { rerender } = render(<StockChart snapshot={makeSnapshot({ events: [milkEvent] })} />)
    expect(history).toHaveBeenCalledTimes(1)
    rerender(<StockChart snapshot={makeSnapshot({ events: [milkEvent, makeEvent({ type: 'SALE', product_id: 'eggs' })] })} />)
    expect(history).toHaveBeenCalledTimes(1)
    rerender(<StockChart snapshot={makeSnapshot({ events: [milkEvent, makeEvent({ type: 'SALE' })] })} />)
    expect(history).toHaveBeenCalledTimes(2)
    rerender(<StockChart snapshot={makeSnapshot({ run_id: 2, events: [] })} />)
    expect(history).toHaveBeenCalledTimes(3)
  })
})
