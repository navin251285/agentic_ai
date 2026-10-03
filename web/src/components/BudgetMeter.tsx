import type { AgentStatus } from '../api/client'

const LEVELS = {
  ok: { fill: 'bg-green', text: 'text-ink' },
  warn: { fill: 'bg-amber', text: 'text-amber-ink' },
  full: { fill: 'bg-red', text: 'text-red-ink' },
}

interface Props {
  agent: AgentStatus
}

/** Gemini call budget: rolling 60 real seconds, limit from the backend (10). Amber at 8, red at 10. */
export function BudgetMeter({ agent }: Props) {
  const { calls_last_60s: calls, call_limit: limit, next_call_allowed_in_s: wait } = agent
  const level = calls >= limit ? 'full' : calls >= limit - 2 ? 'warn' : 'ok'
  const style = LEVELS[level]
  return (
    <div
      data-testid="budget-meter"
      data-level={level}
      className="flex items-center gap-3 rounded-lg border border-border px-3 py-1.5"
    >
      <span className="text-xs text-muted">Calls this minute</span>
      <span className={`font-mono text-[13px] font-medium tabular-nums ${style.text}`}>
        {calls} / {limit}
      </span>
      <div
        role="meter"
        aria-label="Gemini calls in the last minute"
        aria-valuemin={0}
        aria-valuemax={limit}
        aria-valuenow={calls}
        className="flex gap-0.5"
      >
        {Array.from({ length: limit }, (_, i) => (
          <span
            key={i}
            data-filled={i < calls}
            className={`h-3 w-2 rounded-sm transition-colors duration-300 ${i < calls ? style.fill : 'bg-track'}`}
          />
        ))}
      </div>
      {wait > 0 && (
        <span className="font-mono text-xs text-muted tabular-nums">next call in {Math.ceil(wait)}s</span>
      )}
    </div>
  )
}
