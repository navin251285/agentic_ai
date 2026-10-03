import { useMemo } from 'react'

import type { Product, ShopEvent } from '../api/client'
import { feedLines, type FeedTone } from '../lib/events'
import { panel } from './ui'

const TONES: Record<FeedTone, string> = {
  shop: 'bg-ground text-muted',
  alert: 'bg-amber-tint text-amber-ink',
  supplier: 'bg-blue-tint text-blue',
  agent: 'bg-violet-tint text-violet',
  fallback: 'bg-amber-tint text-amber-ink ring-1 ring-violet-line',
  system: 'bg-ground text-ink',
  curveball: 'bg-ink text-white',
}

interface Props {
  events: ShopEvent[]
  products: Product[]
}

export function ActivityFeed({ events, products }: Props) {
  const lines = useMemo(() => {
    const names = Object.fromEntries(products.map((p) => [p.id, p.name]))
    return feedLines(events, names)
  }, [events, products])

  return (
    <section aria-labelledby="feed-title" className={`${panel} p-4`}>
      <div className="mb-3 flex items-baseline justify-between">
        <h2 id="feed-title" className="text-[15px] font-semibold">
          Activity
        </h2>
        <span className="text-xs text-muted">events.csv</span>
      </div>
      {lines.length === 0 ? (
        <p className="text-[13px] text-muted">Nothing yet. Press play.</p>
      ) : (
        <ol className="max-h-[560px] space-y-2.5 overflow-y-auto pr-1">
          {lines.map((line) => (
            <li key={line.key} data-tone={line.tone} className="grid grid-cols-[40px_1fr] gap-2 animate-fade-in">
              <span className="pt-px font-mono text-xs text-muted tabular-nums">{line.time}</span>
              <div>
                <span className={`inline-block rounded px-1.5 py-px text-[10px] font-semibold ${TONES[line.tone]}`}>
                  {line.label}
                </span>
                <p className="mt-0.5 text-[13px] leading-snug">{line.text}</p>
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}
