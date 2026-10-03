// Groups snapshot events for display (feed lines, receipts). No business rules live here.
import type { ShopEvent } from '../api/client'
import { clockTime, customerLabel } from './format'

export type FeedTone = 'shop' | 'alert' | 'supplier' | 'agent' | 'fallback' | 'system' | 'curveball'

export interface FeedLine {
  key: string
  time: string
  label: string
  tone: FeedTone
  text: string
}

export interface ReceiptItem {
  key: string
  name: string
  qty: number
  missed: boolean
}

export interface Receipt {
  key: string
  who: string
  time: string
  items: ReceiptItem[]
}

type Names = Record<string, string>

const SOURCE_PREFIX = /^\[(rules|gemini|fallback)\]\s*/
const AGENT_LABELS = { rules: 'Agent · Rules', gemini: 'Agent · Gemini', fallback: 'Agent · Fallback' }

const eventKey = (e: ShopEvent) => `${e.run_id}|${e.ts_real}|${e.type}|${e.product_id ?? ''}`
const nameOf = (e: ShopEvent, names: Names) => names[e.product_id ?? ''] ?? e.product_id ?? ''

/** "[gemini] Rush hour…" → label "Agent · Gemini", text "Rush hour…". */
function agentLine(e: ShopEvent): Pick<FeedLine, 'label' | 'tone' | 'text'> {
  const match = SOURCE_PREFIX.exec(e.message)
  const source = (match?.[1] ?? 'rules') as keyof typeof AGENT_LABELS
  return {
    label: AGENT_LABELS[source],
    tone: source === 'fallback' ? 'fallback' : 'agent',
    text: e.message.replace(SOURCE_PREFIX, ''),
  }
}

/** "rush_hour → True, agent_mode → gemini" → "rush hour → on, agent mode → gemini". */
function prettyChanges(message: string): string {
  return message
    .replace(/(\w+) → /g, (_, key: string) => `${key.replace(/_/g, ' ')} → `)
    .replace(/→ True\b/g, '→ on')
    .replace(/→ False\b/g, '→ off')
}

/** Feed lines, newest first: one line per customer, one line per reset/scenario load. */
export function feedLines(events: ShopEvent[], names: Names, limit = 30): FeedLine[] {
  const lines: FeedLine[] = []
  const grouped = new Map<string, { line: FeedLine; items: string[]; count: number }>()

  for (const e of events) {
    const base = { key: eventKey(e), time: clockTime(e.shop_time) }
    switch (e.type) {
      case 'SALE': {
        const groupKey = `sale|${e.ref}|${e.sim_s}`
        const group = grouped.get(groupKey)
        if (group) {
          group.items.push(nameOf(e, names))
          group.line.text = `${who(e.ref)} bought ${summarize(group.items)}`
        } else {
          const line: FeedLine = { ...base, label: 'Shop', tone: 'shop', text: `${who(e.ref)} bought ${nameOf(e, names)}` }
          grouped.set(groupKey, { line, items: [nameOf(e, names)], count: 1 })
          lines.push(line)
        }
        break
      }
      case 'SCENARIO_LOADED':
      case 'RESET': {
        const groupKey = `run|${e.type}|${e.sim_s}`
        const title = e.message.split(':')[0] || (e.type === 'RESET' ? 'Reset' : 'Scenario loaded')
        const group = grouped.get(groupKey)
        if (group) {
          group.count += 1
          group.line.text = `${title} · ${group.count} products back to starting stock`
        } else {
          const line: FeedLine = { ...base, label: 'System', tone: 'system', text: `${title} · 1 product back to starting stock` }
          grouped.set(groupKey, { line, items: [], count: 1 })
          lines.push(line)
        }
        break
      }
      case 'ORDER_PLACED':
      case 'AGENT_WAIT':
        lines.push({ ...base, ...agentLine(e) })
        break
      case 'ORDER_CONFIRMED':
      case 'ORDER_SHIPPED':
      case 'DELIVERED':
        lines.push({ ...base, label: 'Supplier', tone: 'supplier', text: e.message })
        break
      case 'MISSED_SALE':
      case 'CROSSED_MARK':
      case 'AGENT_FALLBACK':
        lines.push({ ...base, label: 'Alert', tone: 'alert', text: e.message })
        break
      case 'CURVEBALL':
        lines.push({ ...base, label: 'Curveball', tone: 'curveball', text: e.message })
        break
      case 'EDIT':
      case 'SETTINGS_CHANGED':
        lines.push({ ...base, label: 'System', tone: 'system', text: prettyChanges(e.message) })
        break
    }
  }
  return lines.reverse().slice(0, limit)
}

function who(ref: string): string {
  return ref.startsWith('C-') ? `Customer ${customerLabel(ref)}` : 'Manual sale'
}

/** ["Milk", "Eggs", "Milk"] → "Milk ×2, Eggs". */
function summarize(names: string[]): string {
  const counts = new Map<string, number>()
  for (const n of names) counts.set(n, (counts.get(n) ?? 0) + 1)
  return [...counts].map(([n, c]) => (c > 1 ? `${n} ×${c}` : n)).join(', ')
}

/** Receipts from SALE/MISSED_SALE events grouped by customer, newest first. */
export function receipts(events: ShopEvent[], names: Names): Receipt[] {
  const byKey = new Map<string, Receipt>()
  for (const e of events) {
    if (e.type !== 'SALE' && e.type !== 'MISSED_SALE') continue
    const key = `${e.run_id}|${e.ref}|${e.sim_s}`
    let receipt = byKey.get(key)
    if (!receipt) {
      receipt = { key, who: customerLabel(e.ref), time: clockTime(e.shop_time), items: [] }
      byKey.set(key, receipt)
    }
    const missed = e.type === 'MISSED_SALE'
    const itemKey = `${e.product_id}|${missed}`
    const item = receipt.items.find((i) => i.key === itemKey)
    if (item) item.qty += 1
    else receipt.items.push({ key: itemKey, name: nameOf(e, names), qty: 1, missed })
  }
  return [...byKey.values()].reverse()
}
