import type { Snapshot } from '../api/client'
import { panel } from './ui'

interface Props {
  snapshot: Snapshot
}

export function MetricsRow({ snapshot }: Props) {
  const { counters } = snapshot
  const metrics = [
    { label: 'Sales', value: counters.sales, tone: 'text-ink' },
    { label: 'Missed sales (empty shelf)', value: counters.missed_sales, tone: counters.missed_sales ? 'text-red' : 'text-ink' },
    { label: 'Orders placed by agent', value: counters.orders_placed, tone: 'text-ink' },
    { label: 'Orders on the way', value: snapshot.orders_on_the_way, tone: 'text-blue' },
  ]
  return (
    <section aria-label="Metrics since last reset" className="grid grid-cols-4 gap-3">
      {metrics.map((m) => (
        <div key={m.label} className={`${panel} px-4 py-3`}>
          <p className="text-xs text-muted">{m.label}</p>
          <p className={`mt-1 font-mono text-[26px] leading-none font-medium tabular-nums ${m.tone}`}>{m.value}</p>
        </div>
      ))}
    </section>
  )
}
