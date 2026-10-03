import type { Product } from '../api/client'

export function makeProduct(overrides: Partial<Product> = {}): Product {
  return {
    id: 'milk',
    name: 'Milk',
    stock: 18,
    max_stock: 30,
    reorder_point: 12,
    sell_weight: 5,
    lead_time_s: 60,
    state: 'SELLING',
    badge: null,
    badge_kind: null,
    ...overrides,
  }
}
