import { useEffect, useState, type FormEvent } from 'react'

import { api, ApiError, type Product, type ProductPatch } from '../api/client'
import { act, runAction } from '../store/useShopStore'
import { button } from './ui'

type Field = keyof Required<ProductPatch>

const NUMBER_FIELDS: { field: Field; label: string }[] = [
  { field: 'stock', label: 'Current stock' },
  { field: 'max_stock', label: 'Max capacity' },
  { field: 'reorder_point', label: 'Reorder mark' },
  { field: 'lead_time_s', label: 'Delivery time (sec at 1x)' },
]
const SPEED_WORDS = ['Very slow', 'Very slow', 'Slow', 'Slow', 'Normal', 'Normal', 'Fast', 'Fast', 'Very fast', 'Very fast']
const FIELDS = new Set<string>([...NUMBER_FIELDS.map((f) => f.field), 'sell_weight'])

type Errors = Partial<Record<Field | 'form', string>>

interface Props {
  product: Product
  scenario: string
  onClose: () => void
}

export function EditDrawer({ product, scenario, onClose }: Props) {
  // Only fields the user typed in are kept here; untouched inputs keep following the live value.
  const [draft, setDraft] = useState<Partial<Record<Field, string>>>({})
  const [errors, setErrors] = useState<Errors>({})
  const [saving, setSaving] = useState(false)
  const [scenarios, setScenarios] = useState<string[]>([])
  const [pickedScenario, setPickedScenario] = useState(scenario)

  useEffect(() => {
    api.scenarios().then(setScenarios).catch(() => setScenarios([scenario]))
  }, [scenario])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const value = (f: Field) => draft[f] ?? String(product[f])
  const setField = (f: Field, v: string) => {
    setDraft((d) => ({ ...d, [f]: v }))
    setErrors((e) => ({ ...e, [f]: undefined, form: undefined }))
  }

  const apply = async (e: FormEvent) => {
    e.preventDefault()
    const patch: ProductPatch = {}
    const local: Errors = {}
    for (const [f, raw] of Object.entries(draft) as [Field, string][]) {
      const n = Number(raw)
      if (raw.trim() === '' || !Number.isInteger(n)) local[f] = 'Enter a whole number'
      else if (n !== product[f]) patch[f] = n
    }
    if (Object.keys(local).length) return setErrors(local)
    if (Object.keys(patch).length === 0) return onClose()
    setSaving(true)
    try {
      await runAction(api.editProduct(product.id, patch), false)
      onClose()
    } catch (err) {
      setErrors(toErrors(err))
    } finally {
      setSaving(false)
    }
  }

  /** Quick actions apply at once; the stock input then shows the live value again. */
  const quick = (action: () => ReturnType<typeof api.sell>) => {
    setDraft((d) => {
      const rest = { ...d }
      delete rest.stock
      return rest
    })
    setErrors({})
    act(action())
  }

  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <div className="absolute inset-0 bg-ink/20" onClick={onClose} data-testid="drawer-backdrop" />
      <form
        role="dialog"
        aria-modal="true"
        aria-labelledby="drawer-title"
        onSubmit={apply}
        noValidate
        className="relative flex h-full w-[420px] flex-col gap-5 overflow-y-auto bg-card p-6 shadow-xl animate-fade-in"
      >
        <header className="flex items-start justify-between">
          <div>
            <p className="text-[13px] text-muted">Edit product</p>
            <h2 id="drawer-title" className="text-2xl font-semibold">
              {product.name}
            </h2>
          </div>
          <button type="button" onClick={onClose} aria-label="Close" className={`${button} px-2.5`}>
            ✕
          </button>
        </header>

        <div className="grid grid-cols-2 gap-x-4 gap-y-4">
          {NUMBER_FIELDS.map(({ field, label }, i) => (
            <div key={field}>
              <label className="block">
                <span className="mb-1 block text-[13px] text-muted">{label}</span>
                <input
                type="number"
                inputMode="numeric"
                autoFocus={i === 0}
                value={value(field)}
                onChange={(e) => setField(field, e.target.value)}
                aria-invalid={!!errors[field]}
                className={inputClass(!!errors[field], 'font-mono')}
                />
              </label>
              {errors[field] && <p className="mt-1 text-xs text-red-ink">{errors[field]}</p>}
            </div>
          ))}
        </div>

        <div>
          <label htmlFor="sell-weight" className="mb-1 block text-[13px] text-muted">
            Sell speed
          </label>
          <select
            id="sell-weight"
            value={value('sell_weight')}
            onChange={(e) => setField('sell_weight', e.target.value)}
            aria-invalid={!!errors.sell_weight}
            className={inputClass(!!errors.sell_weight)}
          >
            {SPEED_WORDS.map((word, i) => (
              <option key={i} value={i + 1}>
                {i + 1} · {word}
              </option>
            ))}
          </select>
          {errors.sell_weight && <p className="mt-1 text-xs text-red-ink">{errors.sell_weight}</p>}
        </div>

        <div>
          <p className="mb-1 text-[13px] text-muted">Quick demo actions</p>
          <div className="grid grid-cols-3 gap-2">
            <button type="button" className={button} onClick={() => quick(() => api.sell(product.id, 5))}>
              Sell 5
            </button>
            <button
              type="button"
              className={`${button} border-amber-line bg-amber-tint text-amber-ink hover:bg-amber-tint`}
              onClick={() => quick(() => api.editProduct(product.id, { stock: product.reorder_point }))}
            >
              Drop to mark
            </button>
            <button
              type="button"
              className={`${button} border-red-line bg-red-tint text-red-ink hover:bg-red-tint`}
              onClick={() => quick(() => api.editProduct(product.id, { stock: 0 }))}
            >
              Empty shelf
            </button>
          </div>
        </div>

        <div>
          <label htmlFor="scenario" className="mb-1 block text-[13px] text-muted">
            Load scenario
          </label>
          <div className="flex gap-2">
            <select
              id="scenario"
              value={pickedScenario}
              onChange={(e) => setPickedScenario(e.target.value)}
              className={inputClass(false, 'flex-1')}
            >
              {(scenarios.length ? scenarios : [scenario]).map((s) => (
                <option key={s} value={s}>
                  {s}.csv
                </option>
              ))}
            </select>
            <button
              type="button"
              className={button}
              onClick={() => {
                act(api.loadScenario(pickedScenario))
                onClose()
              }}
            >
              Load
            </button>
          </div>
        </div>

        <p className="rounded-lg bg-ground p-3 text-[13px] text-muted">
          Changes apply on screen instantly. Save writes them to products.csv; every change is also logged in
          events.csv as an EDIT event.
        </p>

        {errors.form && (
          <p role="alert" className="rounded-lg border border-red-line bg-red-wash p-3 text-[13px] text-red-ink">
            {errors.form}
          </p>
        )}

        <footer className="mt-auto grid grid-cols-[1fr_2fr] gap-3">
          <button type="button" onClick={onClose} className={`${button} py-3`}>
            Cancel
          </button>
          <button
            type="submit"
            disabled={saving}
            className="rounded-lg bg-ink py-3 text-[14px] font-medium text-white hover:bg-ink/85 disabled:opacity-50"
          >
            {saving ? 'Saving…' : 'Apply and save to CSV'}
          </button>
        </footer>
      </form>
    </div>
  )
}

function inputClass(invalid: boolean, extra = ''): string {
  const border = invalid ? 'border-red-line bg-red-wash' : 'border-border bg-card'
  return `w-full rounded-lg border px-3 py-2.5 text-[15px] ${border} ${extra}`
}

/** 422 issues with loc ["body", field] go next to that field; anything else is a form-level message. */
function toErrors(err: unknown): Errors {
  if (!(err instanceof ApiError)) return { form: err instanceof Error ? err.message : String(err) }
  const errors: Errors = {}
  const general: string[] = []
  for (const issue of err.issues) {
    const field = String(issue.loc.at(-1))
    if (issue.loc.length >= 2 && FIELDS.has(field)) errors[field as Field] = issue.msg
    else general.push(issue.msg)
  }
  if (general.length || !err.issues.length) errors.form = general.join('; ') || err.message
  return errors
}
