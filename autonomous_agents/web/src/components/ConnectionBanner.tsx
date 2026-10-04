import { useShopStore } from '../store/useShopStore'

/** "Reconnecting…" while the SSE stream is down (EventSource retries by itself), plus failed actions. */
export function ConnectionBanner() {
  const connection = useShopStore((s) => s.connection)
  const actionError = useShopStore((s) => s.actionError)
  const setActionError = useShopStore((s) => s.setActionError)

  if (connection !== 'reconnecting' && !actionError) return null
  return (
    <div className="fixed inset-x-0 top-3 z-50 flex flex-col items-center gap-2" aria-live="assertive">
      {connection === 'reconnecting' && (
        <p role="status" className="flex items-center gap-2 rounded-full border border-amber-line bg-amber-tint px-4 py-1.5 text-[13px] font-medium text-amber-ink shadow-sm">
          <span className="size-2 rounded-full bg-amber animate-thinking" aria-hidden="true" />
          Reconnecting… the screen will catch up when the server is back
        </p>
      )}
      {actionError && (
        <p role="alert" className="flex items-center gap-3 rounded-full border border-red-line bg-red-tint px-4 py-1.5 text-[13px] text-red-ink shadow-sm">
          Action failed: {actionError}
          <button type="button" onClick={() => setActionError(null)} aria-label="Dismiss" className="font-semibold">
            ×
          </button>
        </p>
      )}
    </div>
  )
}
