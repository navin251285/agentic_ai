import { useState } from 'react'
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import type { Snapshot } from '../api/client'
import { useStockHistory } from '../hooks/useStockHistory'
import { formatDuration } from '../lib/format'
import { panel } from './ui'

// SVG attributes need plain colors; these mirror the tokens in index.css.
const C = {
  green: '#2e8b5e',
  amber: '#d98a00',
  amberTint: '#fdefd4',
  amberInk: '#8a5300',
  blue: '#1f4fb8',
  ink: '#17201b',
  muted: '#56615b',
  border: '#dce0da',
}
const LABEL = { fontSize: 12, fontFamily: 'IBM Plex Sans, sans-serif' }
const MONO = { fontSize: 12, fontFamily: 'IBM Plex Mono, monospace', fill: C.muted }

interface Point {
  sim_s: number
  stock: number
  time: string
}

interface Props {
  snapshot: Snapshot
}

export function StockChart({ snapshot }: Props) {
  const [chosenId, setChosenId] = useState<string | null>(null)
  const product = snapshot.products.find((p) => p.id === chosenId) ?? snapshot.products[0]
  const productId = product?.id ?? ''
  // Reload the history whenever the live snapshot shows a new event for this product.
  const latest = snapshot.events.filter((e) => e.product_id === productId).at(-1)
  const shadowNow = snapshot.shadow_stock[productId]
  const history = useStockHistory(productId, snapshot.run_id, `${latest?.ts_real ?? ''}|${shadowNow ?? ''}`)

  if (!product) return null
  const now = snapshot.sim_s
  const order = snapshot.orders.find((o) => o.product_id === product.id)

  // The server's points, plus "now" so the line reaches the present between events.
  const points: Point[] = (history?.points ?? []).map((p) => ({ sim_s: p.sim_s, stock: p.stock_after, time: p.shop_time }))
  points.push({ sim_s: now, stock: product.stock, time: snapshot.shop_time })
  // The rules shop (same customers), as a ghost line to compare with.
  const shadow: Point[] = (history?.shadow_points ?? []).map((p) => ({ sim_s: p.sim_s, stock: p.stock_after, time: p.shop_time }))
  if (shadowNow !== undefined && shadow.length > 0) shadow.push({ sim_s: now, stock: shadowNow, time: snapshot.shop_time })
  const start = points[0].sim_s
  const end = Math.max(now, order?.due_at_s ?? now)
  const pad = Math.max(10, (end - start) * 0.06)

  return (
    <section aria-labelledby="chart-title" className={`${panel} p-4`}>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-baseline gap-3">
          <h2 id="chart-title" className="text-[15px] font-semibold">
            {product.name} · stock over time
          </h2>
          <span className="text-xs text-muted" aria-hidden="true">
            <span className="mr-1 inline-block h-0.5 w-4 bg-green align-middle" /> Agent’s shop
            <span className="mr-1 ml-3 inline-block w-4 border-t-2 border-dashed border-muted align-middle" /> Rules shop
          </span>
        </div>
        <div role="group" aria-label="Chart product" className="flex flex-wrap gap-1.5">
          {snapshot.products.map((p) => {
            const active = p.id === product.id
            return (
              <button
                key={p.id}
                type="button"
                aria-pressed={active}
                onClick={() => setChosenId(p.id)}
                className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors duration-200 ${
                  active ? 'border-ink bg-ink text-white' : 'border-border bg-card text-ink hover:bg-ground'
                }`}
              >
                {p.name}
              </button>
            )
          })}
        </div>
      </div>
      <div className="h-[260px]" data-testid="stock-chart">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={points} margin={{ top: 28, right: 24, bottom: 4, left: 0 }}>
            <CartesianGrid stroke={C.border} strokeDasharray="2 4" vertical={false} />
            <XAxis
              dataKey="sim_s"
              type="number"
              domain={[start, end + pad]}
              ticks={[now]}
              tickFormatter={() => 'Now'}
              tick={{ ...LABEL, fill: C.ink }}
              stroke={C.border}
              allowDataOverflow
            />
            <YAxis
              domain={[0, product.max_stock]}
              ticks={[0, product.reorder_point, product.max_stock]}
              tick={MONO}
              stroke={C.border}
              width={40}
              allowDataOverflow
            />
            <ReferenceArea
              y1={0}
              y2={product.reorder_point}
              fill={C.amberTint}
              fillOpacity={0.7}
              stroke="none"
              label={{ value: 'Danger zone', position: 'insideBottomLeft', fill: C.amberInk, ...LABEL }}
            />
            <ReferenceLine
              y={product.reorder_point}
              stroke={C.ink}
              strokeDasharray="6 4"
              label={{ value: `Reorder mark (${product.reorder_point})`, position: 'insideBottomLeft', fill: C.muted, ...LABEL }}
            />
            {order && (
              <ReferenceLine
                x={order.due_at_s}
                stroke={C.blue}
                strokeWidth={2}
                strokeDasharray="4 4"
                label={{ value: `Arrives in ${formatDuration(order.seconds_left)}`, position: 'top', fill: C.blue, ...LABEL }}
              />
            )}
            <Tooltip content={<PointTooltip />} isAnimationActive={false} />
            {shadow.length > 0 && (
              <Line
                data={shadow}
                type="stepAfter"
                dataKey="stock"
                name="Rules shop"
                stroke={C.muted}
                strokeWidth={1.5}
                strokeDasharray="5 4"
                strokeOpacity={0.7}
                dot={false}
                activeDot={false}
                tooltipType="none"
                isAnimationActive={false}
              />
            )}
            <Line
              type="stepAfter"
              dataKey="stock"
              stroke={C.green}
              strokeWidth={2.5}
              dot={false}
              activeDot={{ r: 4 }}
              isAnimationActive={false}
            />
            {history?.markers.map((m) => {
              const placed = m.type === 'ORDER_PLACED'
              return (
                <ReferenceDot
                  key={`${m.type}-${m.ref}`}
                  x={m.sim_s}
                  y={m.stock_after ?? 0}
                  r={5}
                  fill={placed ? C.amber : C.green}
                  stroke="#fff"
                  strokeWidth={2}
                  label={{ value: placed ? 'Order placed' : `Delivered +${m.qty ?? ''}`, position: 'top', fill: C.ink, ...LABEL }}
                />
              )
            })}
            <ReferenceDot x={now} y={product.stock} r={5} fill={C.ink} stroke="#fff" strokeWidth={2} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </section>
  )
}

function PointTooltip({ active, payload }: { active?: boolean; payload?: { payload: Point }[] }) {
  const point = payload?.[0]?.payload
  if (!active || !point) return null
  return (
    <div className="rounded-md border border-border bg-card px-2 py-1 text-xs shadow-sm">
      <span className="text-muted">{point.time}</span> · <span className="font-mono">{point.stock}</span> in stock
    </div>
  )
}
