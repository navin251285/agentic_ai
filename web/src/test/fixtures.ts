import type { AgentStatus, OpenOrder, Product, ShopEvent, Snapshot } from '../api/client'

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

let seq = 0

/** An event at the given sim_s; ts_real is unique so feed keys never collide. */
export function makeEvent(overrides: Partial<ShopEvent> & Pick<ShopEvent, 'type'>): ShopEvent {
  seq += 1
  return {
    run_id: 1,
    ts_real: `2026-10-03T10:00:00.${String(seq).padStart(6, '0')}Z`,
    sim_s: 10,
    shop_time: 'Day 1 · 08:50',
    product_id: 'milk',
    qty: 1,
    stock_after: 10,
    ref: '',
    message: '',
    ...overrides,
  }
}

export function makeAgent(overrides: Partial<AgentStatus> = {}): AgentStatus {
  return {
    mode: 'rules',
    enabled: true,
    thinking: false,
    llm_ready: true,
    last_latency_ms: null,
    llm_calls: 0,
    fallbacks: 0,
    calls_last_60s: 0,
    call_limit: 10,
    next_call_allowed_in_s: 0,
    pending_products: [],
    ...overrides,
  }
}

export function makeSnapshot(overrides: Partial<Snapshot> = {}): Snapshot {
  return {
    run_id: 1,
    sim_s: 10,
    shop_time: 'Day 1 · 08:50',
    speed: 0,
    last_speed: 1,
    scenario: 'normal_day',
    settings: { rush_hour: false, supplier_delay: false, agent_enabled: true, agent_mode: 'rules', agent_interval_s: 5 },
    counters: { sales: 0, missed_sales: 0, orders_placed: 0 },
    orders_on_the_way: 0,
    next_agent_check_s: 15,
    saved_ago_s: 2,
    products: [makeProduct(), makeProduct({ id: 'eggs', name: 'Eggs', max_stock: 40, reorder_point: 13, stock: 22 })],
    orders: [],
    events: [],
    agent: makeAgent(),
    ...overrides,
  }
}

export function makeOrder(overrides: Partial<OpenOrder> = {}): OpenOrder {
  return {
    id: 'O-0001',
    product_id: 'milk',
    product_name: 'Milk',
    qty: 18,
    status: 'PLACED',
    placed_at_s: 0,
    due_at_s: 60,
    delivered_at_s: null,
    seconds_left: 38,
    ...overrides,
  }
}
