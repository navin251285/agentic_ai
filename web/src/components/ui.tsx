// Small shared controls in the design's style (white bordered buttons, dark segmented selection).
import type { ReactNode } from 'react'

export const panel = 'rounded-xl border border-border bg-card'
export const button =
  'rounded-lg border border-border bg-card px-3 py-2 text-[13px] font-medium hover:bg-ground disabled:opacity-50'

interface SegmentedProps<T extends string | number> {
  label: string
  value: T
  options: { value: T; label: ReactNode; describedBy?: string; title?: string }[]
  onChange: (value: T) => void
  activeClass?: string
}

/** A radio-like group of buttons; the active one is dark, as in the design's speed control. */
export function Segmented<T extends string | number>({
  label,
  value,
  options,
  onChange,
  activeClass = 'bg-ink text-white',
}: SegmentedProps<T>) {
  return (
    <div role="group" aria-label={label} className="flex rounded-lg bg-ground p-1">
      {options.map((o) => {
        const active = o.value === value
        return (
          <button
            key={String(o.value)}
            type="button"
            aria-pressed={active}
            aria-describedby={o.describedBy}
            title={o.title}
            onClick={() => !active && onChange(o.value)}
            className={`rounded-md px-3 py-1.5 text-[13px] font-medium transition-colors duration-200 ${
              active ? activeClass : 'text-muted hover:text-ink'
            }`}
          >
            {o.label}
          </button>
        )
      })}
    </div>
  )
}

interface ToggleProps {
  label: string
  on: boolean
  onChange: (on: boolean) => void
  onClass: string // border/background/text when on
  offClass?: string
}

/** "Rush hour: off" style toggle button from the design. */
export function Toggle({ label, on, onChange, onClass, offClass = '' }: ToggleProps) {
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={() => onChange(!on)}
      className={`${button} transition-colors duration-200 ${on ? onClass : offClass}`}
    >
      {label}: {on ? 'on' : 'off'}
    </button>
  )
}
