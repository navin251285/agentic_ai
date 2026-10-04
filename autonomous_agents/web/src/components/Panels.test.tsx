// MetricsRow, ShopCounter, OrdersPipeline, ActivityFeed, ConnectionBanner.
import { act as actRtl, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { api } from '../api/client'
import { makeEvent, makeOrder, makeSnapshot } from '../test/fixtures'
import { useShopStore } from '../store/useShopStore'
import { ActivityFeed } from './ActivityFeed'
import { ConnectionBanner } from './ConnectionBanner'
import { MetricsRow } from './MetricsRow'
import { OrdersPipeline } from './OrdersPipeline'
import { ShopCounter } from './ShopCounter'

afterEach(() => vi.restoreAllMocks())

describe('MetricsRow', () => {
  it('shows counters and orders on the way', () => {
    render(
      <MetricsRow snapshot={makeSnapshot({ counters: { sales: 142, missed_sales: 2, orders_placed: 6, extra_fees: 0 }, orders_on_the_way: 3 })} />,
    )
    expect(screen.getByText('Sales').nextSibling).toHaveTextContent('142')
    expect(screen.getByText('Missed sales (empty shelf)').nextSibling).toHaveTextContent('2')
    expect(screen.getByText('Missed sales (empty shelf)').nextSibling).toHaveClass('text-red')
    expect(screen.getByText('Orders placed by agent').nextSibling).toHaveTextContent('6')
    expect(screen.getByText('Orders on the way').nextSibling).toHaveTextContent('3')
  })
})

describe('ShopCounter', () => {
  const events = [
    makeEvent({ type: 'SALE', product_id: 'eggs', ref: 'C-0056', sim_s: 4, shop_time: 'Day 1 · 08:20' }),
    makeEvent({ type: 'SALE', product_id: 'milk', ref: 'C-0057', sim_s: 6, shop_time: 'Day 1 · 08:30' }),
    makeEvent({ type: 'MISSED_SALE', product_id: 'eggs', ref: 'C-0057', sim_s: 6, shop_time: 'Day 1 · 08:30' }),
  ]

  it('reveals the latest customer item by item and lists earlier receipts', () => {
    render(<ShopCounter snapshot={makeSnapshot({ events })} />)
    expect(screen.getByText('Now scanning · Customer #57')).toBeInTheDocument()
    const items = screen.getAllByTestId('scan-item')
    expect(items.map((i) => i.textContent)).toEqual(['Milk−1', 'Eggs✕ missed'])
    expect(items[1]).toHaveStyle({ animationDelay: '150ms' })
    expect(screen.getByText('#56 · Eggs')).toBeInTheDocument()
  })

  it('sells 1 of the picked product', () => {
    const sell = vi.spyOn(api, 'sell').mockResolvedValue(makeSnapshot())
    render(<ShopCounter snapshot={makeSnapshot()} />)
    fireEvent.change(screen.getByLabelText('Manual scan (demo)'), { target: { value: 'eggs' } })
    fireEvent.click(screen.getByRole('button', { name: 'Sell 1' }))
    expect(sell).toHaveBeenCalledWith('eggs', 1)
  })
})

describe('OrdersPipeline', () => {
  it('lists open orders soonest first with countdown and stage', () => {
    render(
      <OrdersPipeline
        orders={[
          makeOrder({ id: 'O-2', product_name: 'Biscuits', qty: 30, status: 'CONFIRMED', seconds_left: 110 }),
          makeOrder({ id: 'O-1', product_name: 'Cold drink', qty: 36, status: 'SHIPPED', seconds_left: 12 }),
        ]}
      />,
    )
    const rows = screen.getAllByRole('listitem').filter((li) => li.hasAttribute('data-status'))
    expect(rows[0]).toHaveTextContent('Cold drink × 3612s')
    expect(rows[1]).toHaveTextContent('Biscuits × 301m 50s')
    const steps = (row: HTMLElement) =>
      within(row).getAllByRole('listitem').map((s) => s.getAttribute('data-step'))
    expect(steps(rows[0])).toEqual(['done', 'done', 'current', 'todo'])
    expect(steps(rows[1])).toEqual(['done', 'current', 'todo', 'todo'])
  })

  it('says when nothing is on the way', () => {
    render(<OrdersPipeline orders={[]} />)
    expect(screen.getByText('No orders on the way')).toBeInTheDocument()
  })
})

describe('ActivityFeed', () => {
  it('shows labelled lines, newest first', () => {
    render(
      <ActivityFeed
        products={makeSnapshot().products}
        events={[
          makeEvent({ type: 'ORDER_PLACED', message: '[gemini] Rush hour; ordering milk early.', shop_time: 'Day 1 · 10:36' }),
          makeEvent({ type: 'SALE', ref: 'C-0057', sim_s: 20, shop_time: 'Day 1 · 10:43' }),
        ]}
      />,
    )
    const [first, second] = screen.getAllByRole('listitem')
    expect(first).toHaveTextContent('10:43ShopCustomer #57 bought Milk')
    expect(second).toHaveTextContent('10:36Agent · GeminiRush hour; ordering milk early.')
    expect(second).toHaveAttribute('data-tone', 'agent')
  })
})

describe('ConnectionBanner', () => {
  it('shows "Reconnecting…" while the stream is down and failed actions', () => {
    useShopStore.setState({ connection: 'open', actionError: null })
    const { container } = render(<ConnectionBanner />)
    expect(container).toBeEmptyDOMElement()

    actRtl(() => useShopStore.setState({ connection: 'reconnecting' }))
    expect(screen.getByRole('status')).toHaveTextContent('Reconnecting…')

    actRtl(() => useShopStore.setState({ connection: 'open', actionError: 'Network down' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Network down')
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss' }))
    expect(container).toBeEmptyDOMElement()
  })
})
