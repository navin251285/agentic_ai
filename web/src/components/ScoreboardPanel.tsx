import type { Score, Scoreboard } from '../api/client'
import { rupees } from '../lib/format'
import { panel } from './ui'

interface Props {
  scoreboard: Scoreboard
}

const ROWS: { key: keyof Score; label: string; money: boolean }[] = [
  { key: 'missed_sales', label: 'Missed sales', money: false },
  { key: 'lost_profit', label: 'Lost profit', money: true },
  { key: 'extra_fees', label: 'Backup supplier fees', money: true },
  { key: 'total_cost', label: 'Total cost', money: true },
]

/** The real shop (agent) against the shadow shop run by the rules, with the very same customers. */
export function ScoreboardPanel({ scoreboard }: Props) {
  const { agent, rules, agent_ahead_by: ahead } = scoreboard
  let headline = 'Level with the rules'
  let tone = 'text-muted'
  if (ahead > 0) {
    headline = `Agent ahead by ${rupees(ahead)}`
    tone = 'text-green-ink'
  } else if (ahead < 0) {
    headline = `Rules ahead by ${rupees(-ahead)}`
    tone = 'text-amber-ink'
  }

  return (
    <section aria-labelledby="score-title" className={`${panel} p-4`}>
      <div className="mb-1 flex items-baseline justify-between gap-2">
        <h2 id="score-title" className="text-[15px] font-semibold">
          Agent vs Rules
        </h2>
        <span className="text-xs text-muted">same customers, same news</span>
      </div>
      <p data-testid="score-headline" className={`text-xl font-semibold ${tone}`}>
        {headline}
      </p>
      <table className="mt-2 w-full text-[13px]">
        <thead>
          <tr className="text-xs text-muted">
            <th className="py-1 text-left font-normal">Since reset</th>
            <th className="py-1 text-right font-medium">Agent</th>
            <th className="py-1 text-right font-medium">Rules shop</th>
          </tr>
        </thead>
        <tbody>
          {ROWS.map((r) => {
            const a = agent[r.key]
            const b = rules[r.key]
            const fmt = (n: number) => (r.money ? rupees(n) : String(n))
            return (
              <tr key={r.key} className={`border-t border-border ${r.key === 'total_cost' ? 'font-semibold' : ''}`}>
                <th scope="row" className="py-1.5 text-left font-normal">
                  {r.label}
                </th>
                <td className={`py-1.5 text-right font-mono tabular-nums ${a < b ? 'text-green-ink' : ''}`}>{fmt(a)}</td>
                <td className={`py-1.5 text-right font-mono tabular-nums ${b < a ? 'text-green-ink' : ''}`}>{fmt(b)}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
      {scoreboard.same_brain && (
        <p className="mt-2 text-xs text-muted">Brain is Rules: both shops now decide the same way.</p>
      )}
    </section>
  )
}
