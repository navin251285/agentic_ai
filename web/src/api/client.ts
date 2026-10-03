// Typed fetch wrappers. Types come from FastAPI's OpenAPI schema (npm run gen:types).
import type { components } from './types'

type Schemas = components['schemas']
export type Snapshot = Schemas['Snapshot']
export type Product = Schemas['ProductView']
export type ProductState = Product['state']
export type BadgeKind = NonNullable<Product['badge_kind']>
export type OpenOrder = Schemas['OrderView']
export type ShopEvent = Schemas['Event']
export type AgentStatus = Schemas['AgentStatus']
export type AgentMode = AgentStatus['mode']
export type OrderStatus = Schemas['OrderStatus']
export type History = Schemas['History']
export type ProductPatch = Schemas['ProductPatch']
export type SettingsPatch = Schemas['SettingsPatch']
export type Speed = Schemas['SpeedRequest']['speed']
export type Curveball = Schemas['CurveballView']
export type CurveballPreset = Schemas['CurveballPreset']
export type CurveballRequest = Schemas['CurveballRequest']
export type Scoreboard = Schemas['Scoreboard']
export type Score = Schemas['Score']
export type AgentPlan = Schemas['AgentPlan']
export type PlanStep = Schemas['PlanStep']
type ValidationIssue = Schemas['ValidationError']

/** A non-2xx response; for 422 `issues` holds FastAPI's validation details. */
export class ApiError extends Error {
  readonly status: number
  readonly issues: ValidationIssue[]

  constructor(status: number, message: string, issues: ValidationIssue[] = []) {
    super(message)
    this.status = status
    this.issues = issues
  }
}

/** "/api" normally; under a path prefix (VITE_BASE, e.g. the Jupyter proxy) it follows the page's base. */
export const API_ROOT = `${import.meta.env.BASE_URL}api`

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_ROOT}${path}`, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!res.ok) {
    const data = await res.json().catch(() => null)
    const issues: ValidationIssue[] = Array.isArray(data?.detail) ? data.detail : []
    const message = issues.map((i) => i.msg).join('; ') || data?.detail || res.statusText
    throw new ApiError(res.status, String(message), issues)
  }
  return (await res.json()) as T
}

export const api = {
  snapshot: () => request<Snapshot>('GET', '/snapshot'),
  setSpeed: (speed: Speed) => request<Snapshot>('POST', '/speed', { speed }),
  sell: (product_id: string, qty = 1) => request<Snapshot>('POST', '/sell', { product_id, qty }),
  editProduct: (id: string, patch: ProductPatch) =>
    request<Snapshot>('PATCH', `/products/${encodeURIComponent(id)}`, patch),
  updateSettings: (patch: SettingsPatch) => request<Snapshot>('POST', '/settings', patch),
  scenarios: () => request<string[]>('GET', '/scenarios'),
  loadScenario: (name: string) => request<Snapshot>('POST', '/scenario', { name }),
  reset: () => request<Snapshot>('POST', '/reset'),
  curveballs: () => request<CurveballPreset[]>('GET', '/curveballs'),
  addCurveball: (body: CurveballRequest) => request<Snapshot>('POST', '/curveball', body),
  history: (id: string, windowS = 600) =>
    request<History>('GET', `/history/${encodeURIComponent(id)}?window_s=${windowS}`),
}
