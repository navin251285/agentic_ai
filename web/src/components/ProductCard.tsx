import type { BadgeKind, Product, ProductState } from '../api/client'

interface StateStyle {
  label: string
  card: string // border + background of the whole card
  stock: string // color of the big stock number
  pill: string
  bar: string
}

// Display only: the state and badge text arrive computed in the snapshot.
const STATE_STYLES: Record<ProductState, StateStyle> = {
  SELLING: {
    label: 'Selling',
    card: 'border-border bg-card',
    stock: 'text-ink',
    pill: 'bg-green-tint text-green-ink',
    bar: 'bg-green',
  },
  DANGER: {
    label: 'Danger zone',
    card: 'border-amber-line bg-amber-wash animate-danger-pulse',
    stock: 'text-amber-ink',
    pill: 'bg-amber-tint text-amber-ink',
    bar: 'bg-amber',
  },
  AWAITING: {
    label: 'Order placed · awaiting',
    card: 'border-blue-line bg-card',
    stock: 'text-amber-ink',
    pill: 'bg-blue-tint text-blue',
    bar: 'bg-amber',
  },
  RESTOCKED: {
    label: 'Restocked',
    card: 'border-green-line bg-green-wash',
    stock: 'text-green-ink',
    pill: 'bg-green-tint text-green-ink',
    bar: 'bg-green',
  },
  EMPTY: {
    label: 'Out of stock',
    card: 'border-red-line bg-red-wash',
    stock: 'text-red',
    pill: 'bg-red-tint text-red-ink',
    bar: 'bg-red',
  },
}

const BADGE_STYLES: Record<BadgeKind, string> = {
  arriving: 'bg-blue-tint text-blue',
  agent: 'bg-amber-tint text-amber-ink',
  delivered: 'bg-green-tint text-green-ink',
}

function percent(value: number, max: number): number {
  return Math.min(100, Math.max(0, (value / max) * 100))
}

interface Props {
  product: Product
  onEdit?: (productId: string) => void
}

export function ProductCard({ product, onEdit }: Props) {
  const style = STATE_STYLES[product.state]
  return (
    <article
      data-state={product.state}
      aria-label={`${product.name}: ${style.label}`}
      className={`flex flex-col rounded-xl border p-3.5 transition-colors duration-500 ${style.card}`}
    >
      <header className="flex items-center justify-between">
        <h3 className="text-[15px] font-semibold">{product.name}</h3>
        <button
          type="button"
          onClick={() => onEdit?.(product.id)}
          aria-label={`Edit ${product.name}`}
          className="rounded-md p-1 text-muted hover:bg-ground hover:text-ink"
        >
          <PencilIcon />
        </button>
      </header>

      <p className="mt-2 flex items-baseline gap-1">
        <span className={`font-mono text-[32px] leading-none font-medium tabular-nums ${style.stock}`}>
          {product.stock}
        </span>
        <span className="font-mono text-sm text-muted">/ {product.max_stock}</span>
      </p>

      <div className="relative mt-2.5 h-2 rounded-full bg-track" role="presentation">
        <div
          data-testid="stock-bar"
          className={`h-full rounded-full transition-[width] duration-500 ${style.bar}`}
          style={{ width: `${percent(product.stock, product.max_stock)}%` }}
        />
        <div
          data-testid="reorder-mark"
          className="absolute -top-1 -bottom-1 w-0.5 -translate-x-1/2 rounded bg-ink"
          style={{ left: `${percent(product.reorder_point, product.max_stock)}%` }}
        />
      </div>
      <p className="mt-1.5 text-xs text-muted">Reorder mark {product.reorder_point}</p>

      <span className={`mt-2 self-start rounded-full px-2.5 py-0.5 text-xs font-medium ${style.pill}`}>
        {style.label}
      </span>

      {product.badge && product.badge_kind && (
        <p
          data-badge={product.badge_kind}
          className={`mt-2 flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[13px] ${BADGE_STYLES[product.badge_kind]}`}
        >
          {product.badge_kind === 'arriving' && <TruckIcon />}
          <span className="tabular-nums">{product.badge}</span>
        </p>
      )}
    </article>
  )
}

function PencilIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M17 3a2.85 2.85 0 0 1 4 4L7.5 20.5 2 22l1.5-5.5Z" />
    </svg>
  )
}

function TruckIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className="shrink-0">
      <path d="M14 18V6a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v11a1 1 0 0 0 1 1h2" />
      <path d="M15 18H9" />
      <path d="M19 18h2a1 1 0 0 0 1-1v-3.65a1 1 0 0 0-.22-.62l-3.48-4.35A1 1 0 0 0 17.52 8H14" />
      <circle cx="17" cy="18" r="2" />
      <circle cx="7" cy="18" r="2" />
    </svg>
  )
}
