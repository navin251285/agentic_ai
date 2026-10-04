import { api, type Snapshot, type Speed } from '../api/client'
import { act } from '../store/useShopStore'
import { AgentBar, GEMINI_5X_HINT_ID } from './AgentBar'
import { button, panel, Segmented, Toggle } from './ui'

const SPEEDS: { value: Speed; label: string }[] = [
  { value: 0, label: 'Pause' },
  { value: 0.5, label: '0.5x' },
  { value: 1, label: '1x' },
  { value: 5, label: '5x' },
]
const PRESSURE_ON = 'border-amber-line bg-amber-tint text-amber-ink hover:bg-amber-tint'

interface Props {
  snapshot: Snapshot
}

export function TopBar({ snapshot }: Props) {
  const { settings, saved_ago_s } = snapshot
  const gemini = snapshot.agent.mode === 'gemini'
  const saved = saved_ago_s == null ? 'not saved yet' : `saved ${Math.floor(saved_ago_s)}s ago`

  return (
    <header className={`${panel} space-y-3 px-5 py-4`}>
      <div className="flex flex-wrap items-center gap-3">
        <div className="mr-auto">
          <h1 className="text-lg font-semibold">Corner Store · Restock Agent</h1>
          <p className="text-xs text-muted">
            Data: products.csv ({snapshot.scenario}) · <span data-testid="saved-ago">{saved}</span> · 1 sim second
            = 5 shop minutes
          </p>
        </div>
        <div className="text-right">
          <p className="text-[11px] text-muted">Shop time</p>
          <p className="font-mono text-xl leading-tight font-medium tabular-nums">{snapshot.shop_time}</p>
        </div>
        <Segmented<Speed>
          label="Speed"
          value={snapshot.speed}
          onChange={(speed) => act(api.setSpeed(speed))}
          options={SPEEDS.map((s) =>
            s.value === 5 && gemini
              ? {
                  ...s,
                  label: (
                    <>
                      5x
                      <span aria-hidden="true" className="ml-1 inline-block size-1.5 rounded-full bg-amber align-middle" />
                    </>
                  ),
                  describedBy: GEMINI_5X_HINT_ID,
                  title: 'Gemini is limited at 5x — rules will cover most decisions',
                }
              : s,
          )}
        />
        <Toggle
          label="Rush hour"
          on={settings.rush_hour}
          onChange={(on) => act(api.updateSettings({ rush_hour: on }))}
          onClass={PRESSURE_ON}
        />
        <Toggle
          label="Supplier delay"
          on={settings.supplier_delay}
          onChange={(on) => act(api.updateSettings({ supplier_delay: on }))}
          onClass={PRESSURE_ON}
        />
        <button
          type="button"
          className={button}
          title={`Reload ${snapshot.scenario}.csv and start a new run`}
          onClick={() => act(api.reset())}
        >
          Reset
        </button>
      </div>
      <AgentBar snapshot={snapshot} />
    </header>
  )
}
