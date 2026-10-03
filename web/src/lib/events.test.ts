import { describe, expect, it } from 'vitest'

import { makeEvent } from '../test/fixtures'
import { feedLines, receipts } from './events'
import { clockTime, customerLabel, formatDuration } from './format'

const names = { milk: 'Milk', eggs: 'Eggs', chips: 'Chips', bread: 'Bread' }

const sale = (product_id: string, ref: string, sim_s: number) =>
  makeEvent({ type: 'SALE', product_id, ref, sim_s, shop_time: `Day 1 · 09:${String(sim_s).padStart(2, '0')}` })

describe('format', () => {
  it('formats durations, clock times and customer refs', () => {
    expect(formatDuration(12)).toBe('12s')
    expect(formatDuration(37.2)).toBe('38s')
    expect(formatDuration(110)).toBe('1m 50s')
    expect(formatDuration(120)).toBe('2m')
    expect(clockTime('Day 2 · 07:05')).toBe('07:05')
    expect(customerLabel('C-0057')).toBe('#57')
    expect(customerLabel('MANUAL')).toBe('Manual')
  })
})

describe('feedLines', () => {
  it('writes ONE line per customer, newest first', () => {
    const lines = feedLines(
      [sale('milk', 'C-0056', 10), sale('milk', 'C-0057', 12), sale('eggs', 'C-0057', 12), sale('chips', 'C-0057', 12)],
      names,
    )
    expect(lines.map((l) => l.text)).toEqual(['Customer #57 bought Milk, Eggs, Chips', 'Customer #56 bought Milk'])
    expect(lines[0]).toMatchObject({ label: 'Shop', tone: 'shop', time: '09:12' })
  })

  it('counts repeated manual units', () => {
    const lines = feedLines([sale('milk', 'MANUAL', 5), sale('milk', 'MANUAL', 5)], names)
    expect(lines[0].text).toBe('Manual sale bought Milk ×2')
  })

  it.each([
    ['[rules] Milk at 12. Ordered 18.', 'Agent · Rules', 'agent'],
    ['[gemini] Rush hour; ordering early.', 'Agent · Gemini', 'agent'],
    ['[fallback] Gemini budget reached', 'Agent · Fallback', 'fallback'],
  ])('labels agent orders by source: %s', (message, label, tone) => {
    const [line] = feedLines([makeEvent({ type: 'ORDER_PLACED', message })], names)
    expect(line).toMatchObject({ label, tone })
    expect(line.text).not.toMatch(/^\[/)
  })

  it('labels Gemini waits, supplier steps, alerts and system events', () => {
    const lines = feedLines(
      [
        makeEvent({ type: 'AGENT_WAIT', message: '[gemini] Plenty left for now' }),
        makeEvent({ type: 'ORDER_SHIPPED', message: 'Milk order shipped' }),
        makeEvent({ type: 'DELIVERED', message: 'Delivered 18 Milk' }),
        makeEvent({ type: 'MISSED_SALE', message: 'Customer #3 wanted Milk: out of stock' }),
        makeEvent({ type: 'CROSSED_MARK', message: 'Milk at 12, reached its mark 12' }),
        makeEvent({ type: 'AGENT_FALLBACK', message: 'Gemini unavailable (timeout); rules decided' }),
        makeEvent({ type: 'SETTINGS_CHANGED', product_id: null, message: 'rush_hour → True, agent_mode → gemini' }),
      ],
      names,
    ).reverse()
    expect(lines.map((l) => l.label)).toEqual([
      'Agent · Gemini',
      'Supplier',
      'Supplier',
      'Alert',
      'Alert',
      'Alert',
      'System',
    ])
    expect(lines[6].text).toBe('rush hour → on, agent mode → gemini')
  })

  it('collapses per-product RESET rows into one line', () => {
    const resets = ['milk', 'eggs', 'bread'].map((id) =>
      makeEvent({ type: 'RESET', product_id: id, sim_s: 0, message: `Reset: ${id} starts at 10` }),
    )
    const lines = feedLines(resets, names)
    expect(lines).toHaveLength(1)
    expect(lines[0]).toMatchObject({ label: 'System', text: 'Reset · 3 products back to starting stock' })
  })

  it('keeps only the latest lines', () => {
    const events = Array.from({ length: 40 }, (_, i) => sale('milk', `C-${String(i + 1).padStart(4, '0')}`, i))
    const lines = feedLines(events, names)
    expect(lines).toHaveLength(30)
    expect(lines[0].text).toBe('Customer #40 bought Milk')
  })
})

describe('receipts', () => {
  it('groups sales and missed sales per customer, newest first', () => {
    const result = receipts(
      [
        sale('bread', 'C-0001', 2),
        sale('milk', 'C-0002', 4),
        makeEvent({ type: 'MISSED_SALE', product_id: 'chips', ref: 'C-0002', sim_s: 4 }),
        makeEvent({ type: 'CROSSED_MARK', product_id: 'milk', sim_s: 4 }),
      ],
      names,
    )
    expect(result).toHaveLength(2)
    expect(result[0].who).toBe('#2')
    expect(result[0].items).toEqual([
      expect.objectContaining({ name: 'Milk', qty: 1, missed: false }),
      expect.objectContaining({ name: 'Chips', qty: 1, missed: true }),
    ])
    expect(result[1].items.map((i) => i.name)).toEqual(['Bread'])
  })
})
