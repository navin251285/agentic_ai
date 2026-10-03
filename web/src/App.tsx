import { ProductGrid } from './components/ProductGrid'
import { useLiveState } from './hooks/useLiveState'
import { useShopStore } from './store/useShopStore'

export default function App() {
  useLiveState()
  const snapshot = useShopStore((s) => s.snapshot)

  return (
    <main className="mx-auto max-w-[1440px] p-4">
      {/* Phase 6 adds the TopBar and MetricsRow above, ShopCounter left and OrdersPipeline/ActivityFeed right. */}
      <div className="grid grid-cols-[260px_minmax(0,1fr)_300px] gap-4">
        <div className="col-start-2">
          {snapshot ? (
            <ProductGrid products={snapshot.products} />
          ) : (
            <p className="py-16 text-center text-muted">Connecting to the shop…</p>
          )}
        </div>
      </div>
    </main>
  )
}
