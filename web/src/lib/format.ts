// Display formatting only. Every value here already arrives computed in the snapshot.

/** 12 → "12s", 110 → "1m 50s", 120 → "2m". */
export function formatDuration(seconds: number): string {
  const s = Math.max(0, Math.ceil(seconds))
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  const rest = s % 60
  return rest ? `${m}m ${rest}s` : `${m}m`
}

/** "Day 1 · 14:52" → "14:52". */
export function clockTime(shopTime: string): string {
  return shopTime.split(' · ').at(-1) ?? shopTime
}

/** "C-0057" → "#57"; "MANUAL" → "Manual". */
export function customerLabel(ref: string): string {
  return ref.startsWith('C-') ? `#${Number(ref.slice(2))}` : 'Manual'
}

/** 1240 → "₹1,240"; −48 → "−₹48". */
export function rupees(amount: number): string {
  const text = `₹${Math.abs(amount).toLocaleString('en-IN')}`
  return amount < 0 ? `−${text}` : text
}
