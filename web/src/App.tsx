import { useCallback, useState } from 'react'

import { ActivityFeed } from './components/ActivityFeed'
import { ConnectionBanner } from './components/ConnectionBanner'
import { EditDrawer } from './components/EditDrawer'
import { MetricsRow } from './components/MetricsRow'
import { OrdersPipeline } from './components/OrdersPipeline'
import { ProductGrid } from './components/ProductGrid'
import { ShopCounter } from './components/ShopCounter'
import { TopBar } from './components/TopBar'
import { useLiveState } from './hooks/useLiveState'
import { useShopStore } from './store/useShopStore'

export default function App() {
  useLiveState()
  const snapshot = useShopStore((s) => s.snapshot)
  const [editingId, setEditingId] = useState<string | null>(null)
  const closeDrawer = useCallback(() => setEditingId(null), [])
  const editing = snapshot?.products.find((p) => p.id === editingId)

  return (
    <>
      <ConnectionBanner />
      {snapshot ? (
        <main className="mx-auto max-w-[1440px] space-y-4 p-4">
          <TopBar snapshot={snapshot} />
          <MetricsRow snapshot={snapshot} />
          {/* Phase 7 adds the StockChart below this row. */}
          <div className="grid grid-cols-[260px_minmax(0,1fr)_300px] items-start gap-4">
            <ShopCounter snapshot={snapshot} />
            <ProductGrid products={snapshot.products} onEdit={setEditingId} />
            <div className="space-y-4">
              <OrdersPipeline orders={snapshot.orders} />
              <ActivityFeed events={snapshot.events} products={snapshot.products} />
            </div>
          </div>
        </main>
      ) : (
        <p className="py-16 text-center text-muted">Connecting to the shop…</p>
      )}
      {editing && snapshot && (
        <EditDrawer key={editing.id} product={editing} scenario={snapshot.scenario} onClose={closeDrawer} />
      )}
    </>
  )
}
