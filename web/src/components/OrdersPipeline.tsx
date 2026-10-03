import type { OpenOrder, OrderStatus } from '../api/client'
import { formatDuration } from '../lib/format'
import { panel } from './ui'

const STEPS: { status: OrderStatus; label: string }[] = [
  { status: 'PLACED', label: 'Placed' },
  { status: 'CONFIRMED', label: 'Confirmed' },
  { status: 'SHIPPED', label: 'Shipped' },
  { status: 'DELIVERED', label: 'Delivered' },
]

interface Props {
  orders: OpenOrder[]
}

export function OrdersPipeline({ orders }: Props) {
  const sorted = [...orders].sort((a, b) => a.seconds_left - b.seconds_left)
  return (
    <section aria-labelledby="pipeline-title" className={`${panel} p-4`}>
      <div className="mb-3 flex items-baseline justify-between">
        <h2 id="pipeline-title" className="text-[15px] font-semibold">
          Orders on the way
        </h2>
        <span className="text-xs text-muted">Supplier</span>
      </div>
      {sorted.length === 0 ? (
        <p className="text-[13px] text-muted">No orders on the way</p>
      ) : (
        <ul className="space-y-2">
          {sorted.map((o) => (
            <OrderRow key={o.id} order={o} />
          ))}
        </ul>
      )}
    </section>
  )
}

function OrderRow({ order }: { order: OpenOrder }) {
  // Steps already reached are solid; the current step is light (in progress), as in the design.
  const current = STEPS.findIndex((s) => s.status === order.status)
  return (
    <li data-status={order.status} className="rounded-lg border border-border px-3 py-2.5 animate-fade-in">
      <div className="flex items-baseline justify-between">
        <span className="text-[13px] font-semibold">
          {order.product_name} × {order.qty}
          {order.supplier === 'backup' && (
            <span className="ml-1.5 rounded bg-violet-tint px-1 py-px text-[10px] font-semibold text-violet">Backup</span>
          )}
        </span>
        <span className="font-mono text-[13px] font-medium text-blue tabular-nums">
          {formatDuration(order.seconds_left)}
        </span>
      </div>
      <ol className="mt-2 grid grid-cols-4 gap-1" aria-label={`${order.product_name} order: ${order.status.toLowerCase()}`}>
        {STEPS.map((step, i) => (
          <li key={step.status} data-step={i < current ? 'done' : i === current ? 'current' : 'todo'}>
            <span
              className={`block h-1 rounded-full transition-colors duration-500 ${
                i < current ? 'bg-blue' : i === current ? 'bg-blue-line' : 'bg-track'
              }`}
            />
            <span className={`mt-1 block text-[10px] ${i <= current ? 'text-blue' : 'text-muted'}`}>{step.label}</span>
          </li>
        ))}
      </ol>
    </li>
  )
}
