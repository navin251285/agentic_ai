import type { Product } from '../api/client'
import { ProductCard } from './ProductCard'

const LEGEND = [
  { label: 'Selling', dot: 'bg-green' },
  { label: 'Danger zone (below mark)', dot: 'bg-amber' },
  { label: 'Order awaiting', dot: 'bg-blue' },
  { label: 'Empty', dot: 'bg-red' },
]

interface Props {
  products: Product[]
  onEdit?: (productId: string) => void
}

export function ProductGrid({ products, onEdit }: Props) {
  return (
    <section aria-labelledby="inventory-title">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 id="inventory-title" className="text-[15px] font-semibold">
          Inventory · {products.length} products
        </h2>
        <ul className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
          {LEGEND.map((item) => (
            <li key={item.label} className="flex items-center gap-1.5">
              <span className={`size-2 rounded-full ${item.dot}`} aria-hidden="true" />
              {item.label}
            </li>
          ))}
          <li className="flex items-center gap-1.5">
            <span className="h-0.5 w-3 rounded bg-ink" aria-hidden="true" />
            Reorder mark
          </li>
        </ul>
      </div>
      <div className="grid grid-cols-4 gap-3">
        {products.map((product) => (
          <ProductCard key={product.id} product={product} onEdit={onEdit} />
        ))}
      </div>
    </section>
  )
}
