import { useMemo, useState } from 'react'

import { api, type Snapshot } from '../api/client'
import { receipts as toReceipts, type Receipt } from '../lib/events'
import { act } from '../store/useShopStore'
import { panel } from './ui'

const RECENT = 5
const STAGGER_MS = 150

interface Props {
  snapshot: Snapshot
}

export function ShopCounter({ snapshot }: Props) {
  const { products, events } = snapshot
  const receipts = useMemo(() => {
    const names = Object.fromEntries(products.map((p) => [p.id, p.name]))
    return toReceipts(events, names)
  }, [products, events])
  const [current, ...older] = receipts

  return (
    <section aria-labelledby="counter-title" className={`${panel} space-y-4 p-4`}>
      <h2 id="counter-title" className="text-[15px] font-semibold">
        Shop counter
      </h2>

      <div className="rounded-lg border border-border p-3" aria-live="polite">
        {current ? <NowScanning key={current.key} receipt={current} /> : <p className="text-[13px] text-muted">Waiting for customers…</p>}
      </div>

      <div>
        <h3 className="mb-1.5 text-xs text-muted">Recent receipts</h3>
        {older.length === 0 ? (
          <p className="text-[13px] text-muted">None yet</p>
        ) : (
          <ul className="space-y-1 text-[13px]">
            {older.slice(0, RECENT).map((r) => (
              <li key={r.key} className="flex justify-between gap-2 animate-fade-in">
                <span className="truncate">
                  {r.who} · {r.items.map((i) => (i.missed ? `${i.name} ✕ missed` : itemName(i.name, i.qty))).join(', ')}
                </span>
                <span className="font-mono text-muted tabular-nums">{r.time}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <ManualSell products={products} />
    </section>
  )
}

function NowScanning({ receipt }: { receipt: Receipt }) {
  const title = receipt.who === 'Manual' ? 'Manual sale' : `Customer ${receipt.who}`
  return (
    <>
      <p className="mb-1.5 flex justify-between text-xs text-muted">
        <span>Now scanning · {title}</span>
        <span className="font-mono tabular-nums">{receipt.time}</span>
      </p>
      <ul className="space-y-0.5 text-[13px]">
        {receipt.items.map((item, i) => (
          <li
            key={item.key}
            data-testid="scan-item"
            className="-mx-1.5 flex justify-between rounded px-1.5 py-0.5 animate-scan-in"
            style={{ animationDelay: `${i * STAGGER_MS}ms` }}
          >
            <span>{itemName(item.name, item.qty)}</span>
            {item.missed ? (
              <span className="text-xs font-medium text-red-ink">✕ missed</span>
            ) : (
              <span className="font-mono font-medium text-red-ink">−{item.qty}</span>
            )}
          </li>
        ))}
      </ul>
    </>
  )
}

function ManualSell({ products }: Pick<Snapshot, 'products'>) {
  const [picked, setPicked] = useState('')
  const productId = picked || products[0]?.id || ''
  return (
    <div className="border-t border-border pt-3">
      <label htmlFor="manual-product" className="mb-1.5 block text-xs text-muted">
        Manual scan (demo)
      </label>
      <div className="flex gap-2">
        <select
          id="manual-product"
          value={productId}
          onChange={(e) => setPicked(e.target.value)}
          className="min-w-0 flex-1 rounded-lg border border-border bg-card px-2 py-2 text-[13px]"
        >
          {products.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
        <button
          type="button"
          disabled={!productId}
          onClick={() => act(api.sell(productId, 1))}
          className="rounded-lg bg-ink px-3 py-2 text-[13px] font-medium text-white hover:bg-ink/85 disabled:opacity-50"
        >
          Sell 1
        </button>
      </div>
    </div>
  )
}

const itemName = (name: string, qty: number) => (qty > 1 ? `${name} ×${qty}` : name)
