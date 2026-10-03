import { api, type AgentMode, type AgentStatus, type Snapshot } from '../api/client'
import { act } from '../store/useShopStore'
import { BudgetMeter } from './BudgetMeter'
import { Segmented, Toggle } from './ui'

export const GEMINI_5X_HINT_ID = 'gemini-5x-hint'

interface Props {
  snapshot: Snapshot
}

/** Second row of the top bar: agent on/off, brain switch, status chip, Gemini budget meter. */
export function AgentBar({ snapshot }: Props) {
  const { agent } = snapshot
  const gemini = agent.mode === 'gemini'
  return (
    <div className="flex flex-wrap items-center gap-3 border-t border-border pt-3">
      <Toggle
        label="Agent"
        on={agent.enabled}
        onChange={(on) => act(api.updateSettings({ agent_enabled: on }))}
        onClass="border-green-line bg-green-tint text-green-ink hover:bg-green-tint"
        offClass="border-amber-line bg-amber-tint text-amber-ink hover:bg-amber-tint"
      />
      <div className="flex items-center gap-2">
        <span className="text-xs text-muted">Brain</span>
        <Segmented<AgentMode>
          label="Agent brain"
          value={agent.mode}
          onChange={(mode) => act(api.updateSettings({ agent_mode: mode }))}
          activeClass={gemini ? 'bg-violet text-white' : 'bg-ink text-white'}
          options={[
            { value: 'rules', label: 'Rules' },
            {
              value: 'gemini',
              label: (
                <>
                  Gemini
                  {!agent.llm_ready && <span className="ml-1 text-[11px] font-normal opacity-80"> warming up</span>}
                </>
              ),
            },
          ]}
        />
      </div>
      <AgentStatusChip agent={agent} />
      {gemini && <BudgetMeter agent={agent} />}
      {gemini && (
        // Visible only while at 5x; otherwise kept for screen readers as the 5x button's description.
        <p id={GEMINI_5X_HINT_ID} className={snapshot.speed === 5 ? 'ml-auto text-xs text-amber-ink' : 'sr-only'}>
          Gemini is limited at 5x — rules will cover most decisions
        </p>
      )}
    </div>
  )
}

export function AgentStatusChip({ agent }: { agent: AgentStatus }) {
  const gemini = agent.mode === 'gemini'
  let dot = 'bg-green'
  let status = gemini ? 'Gemini · idle' : 'Rules · decides instantly'
  if (!agent.enabled) {
    dot = 'bg-muted'
    status = 'Agent is off'
  } else if (agent.thinking) {
    dot = 'bg-violet animate-thinking'
    status = 'Gemini thinking…'
  } else if (gemini && agent.last_latency_ms != null) {
    status = `Gemini · last ${Math.round(agent.last_latency_ms)} ms`
  }
  const pending = agent.pending_products?.length ?? 0
  return (
    <div
      data-testid="agent-chip"
      role="status"
      className="flex items-center gap-2 rounded-full border border-border bg-card px-3 py-1.5 text-xs"
    >
      <span className={`size-2 rounded-full ${dot}`} aria-hidden="true" />
      <span className="font-medium">{status}</span>
      <span className="font-mono text-muted tabular-nums">
        {plural(agent.llm_calls, 'call')} · {plural(agent.fallbacks, 'fallback')}
        {gemini && pending > 0 && ` · ${pending} pending`}
      </span>
    </div>
  )
}

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`
