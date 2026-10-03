import { useEffect, useState, type FormEvent } from 'react'

import { api, type CurveballPreset, type CurveballRequest, type Snapshot } from '../api/client'
import { formatDuration } from '../lib/format'
import { runAction } from '../store/useShopStore'
import { button, panel } from './ui'

interface Props {
  snapshot: Snapshot
}

/** Throw the agent news nobody wrote a handler for: presets change the world, typed text only informs it. */
export function CurveballPanel({ snapshot }: Props) {
  const [presets, setPresets] = useState<CurveballPreset[]>([])
  const [text, setText] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.curveballs().then(setPresets, () => setPresets([]))
  }, [])

  const send = async (body: CurveballRequest) => {
    setBusy(true)
    try {
      await runAction(api.addCurveball(body), false)
      setText('')
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (text.trim()) void send({ text: text.trim() })
  }

  return (
    <section aria-labelledby="curveball-title" className={`${panel} p-4`}>
      <div className="mb-3 flex items-baseline justify-between">
        <h2 id="curveball-title" className="text-[15px] font-semibold">
          Curveball
        </h2>
        <span className="text-xs text-muted">news the agent was never programmed for</span>
      </div>

      <div className="flex flex-wrap gap-2">
        {presets.map((p) => (
          <button
            key={p.id}
            type="button"
            className={button}
            disabled={busy}
            title={`${p.text} Effect: ${p.effect}`}
            onClick={() => void send({ preset: p.id })}
          >
            {p.title}
          </button>
        ))}
      </div>

      <form onSubmit={submit} className="mt-2 flex gap-2">
        <label htmlFor="curveball-text" className="sr-only">
          Your own news for the agent
        </label>
        <input
          id="curveball-text"
          value={text}
          maxLength={200}
          onChange={(e) => setText(e.target.value)}
          placeholder="Or type news: “School holiday tomorrow…”"
          className="min-w-0 flex-1 rounded-lg border border-border bg-card px-3 py-2 text-[13px]"
        />
        <button type="submit" disabled={busy || text.trim().length < 3} className={`${button} bg-ink text-white hover:bg-ink`}>
          Send
        </button>
      </form>
      {error && (
        <p role="alert" className="mt-1.5 text-xs text-red-ink">
          {error}
        </p>
      )}
      {snapshot.agent.mode === 'rules' && (
        <p className="mt-2 text-xs text-amber-ink">The Rules brain can’t read news — switch the brain to Gemini.</p>
      )}

      {snapshot.curveballs.length > 0 && (
        <ul className="mt-3 space-y-1.5" aria-label="Active curveballs">
          {snapshot.curveballs.map((c) => (
            <li key={c.id} className="rounded-lg bg-ground px-3 py-2 animate-fade-in">
              <div className="flex items-baseline justify-between gap-2">
                <span className="text-[13px] font-semibold">{c.title}</span>
                <span className="font-mono text-xs text-muted tabular-nums">{formatDuration(c.seconds_left)} left</span>
              </div>
              {c.preset && <p className="text-xs text-muted">{c.text}</p>}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
