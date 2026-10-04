import type { AgentStatus, PlanStep } from '../api/client'
import { clockTime } from '../lib/format'
import { panel } from './ui'

interface Props {
  agent: AgentStatus
}

/** The agent's latest reasoning: what triggered it, how it read the situation, and what it did. */
export function AgentPlanCard({ agent }: Props) {
  const { plan } = agent
  const orders = plan?.steps.filter((s) => s.action === 'order') ?? []
  const waits = plan?.steps.filter((s) => s.action === 'wait') ?? []

  return (
    <section aria-labelledby="plan-title" className={`${panel} p-4`}>
      <div className="mb-3 flex items-baseline justify-between gap-2">
        <h2 id="plan-title" className="text-[15px] font-semibold">
          Agent plan
        </h2>
        {plan && agent.mode === 'gemini' && (
          <span className="text-xs text-muted">
            <span
              className={`mr-1.5 rounded px-1.5 py-px text-[10px] font-semibold ${
                plan.trigger.startsWith('Curveball') ? 'bg-ink text-white' : 'bg-violet-tint text-violet'
              }`}
            >
              {plan.trigger}
            </span>
            <span className="font-mono tabular-nums">{clockTime(plan.shop_time)}</span>
          </span>
        )}
      </div>

      {agent.mode === 'rules' ? (
        <p className="text-[13px] text-muted">
          The Rules brain follows a fixed formula; it doesn’t plan. Switch the brain to Gemini to see the agent think.
        </p>
      ) : !plan ? (
        <p className="text-[13px] text-muted">
          {agent.thinking ? 'Gemini is thinking…' : 'Waiting for Gemini’s first decision…'}
        </p>
      ) : (
        <div key={`${plan.sim_s}|${plan.trigger}`} className="animate-fade-in">
          <blockquote className="border-l-2 border-violet-line pl-3 text-[13px] leading-snug">{plan.situation}</blockquote>
          {orders.length > 0 && (
            <ol className="mt-3 space-y-2" aria-label="Orders in this plan">
              {orders.map((s) => (
                <Step key={s.product_id} step={s} />
              ))}
            </ol>
          )}
          {waits.length > 0 && (
            <p className="mt-2 text-xs text-muted">
              Waiting on: {waits.map((s) => s.product_name).join(', ')}
            </p>
          )}
          {plan.steps.length === 0 && <p className="mt-2 text-xs text-muted">No action needed.</p>}
        </div>
      )}
    </section>
  )
}

function Step({ step }: { step: PlanStep }) {
  const fallback = step.source === 'fallback'
  return (
    <li className="text-[13px] leading-snug">
      <span className="font-semibold">{step.product_name}</span> · order {step.qty} from{' '}
      <span
        className={`rounded px-1 py-px text-[11px] font-semibold ${
          step.supplier === 'backup' ? 'bg-violet-tint text-violet' : 'bg-ground text-ink'
        }`}
      >
        {step.supplier === 'backup' ? 'backup' : 'main'}
      </span>
      {fallback && (
        <span className="ml-1 rounded bg-amber-tint px-1 py-px text-[11px] font-semibold text-amber-ink">rules fallback</span>
      )}
      <span className="block text-xs text-muted">{step.reason}</span>
    </li>
  )
}
