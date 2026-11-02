import { request } from './client'

export type RunStatus = 'queued' | 'running' | 'awaiting_po' | 'completed' | 'failed'
export type Decision = 'accept' | 'review' | 'reject'
export type StageStatus = 'pending' | 'running' | 'waiting' | 'completed' | 'failed' | 'skipped'
export type StageName =
  | 'extraction'
  | 'po_detection'
  | 'po_confirmation'
  | 'verification'
  | 'checks'
  | 'decision'

export type RunFilter = 'all' | 'accept' | 'review' | 'reject' | 'awaiting_po'

export interface Stage {
  name: StageName
  status: StageStatus
  summary: string | null
  started_at: string | null
  finished_at: string | null
}

export interface CheckResult {
  name: string
  outcome: 'pass' | Exclude<Decision, 'accept'>
  message: string
}

export interface LineItem {
  description: string
  quantity: number | null
  unit_price: number | null
  discount_percent?: number | null
  amount: number | null
}

export interface InvoiceFacts {
  line_items: LineItem[]
  charges: { label: string; amount: number }[]
  invoice_number: string | null
  invoice_date: string | null
  vendor: string | null
  currency: string | null
  subtotal: number | null
  tax: number | null
  total: number | null
}

export interface PoFacts {
  vendor: string | null
  total: number | null
  total_field: string | null
  currency: string | null
}

/** What one AI model read, and what the rules would decide from its reading alone. */
export interface ModelVote {
  model: string
  status: 'answered' | 'failed'
  seconds: number
  chosen: boolean
  decision: Decision | null
  reasons: string[]
  invoice_number: string | null
  total: number | null
  vendor_match: 'yes' | 'no' | 'unclear' | null
  error: string | null
}

export interface Run {
  id: string
  document_id: string
  filename: string
  status: RunStatus
  stages: Stage[]
  po_prompt: string | null
  po_suggestions: string[]
  po_number: string | null
  po_source: 'detected' | 'user_supplied' | null
  verification: { invoice: InvoiceFacts; purchase_order: PoFacts } | null
  checks: CheckResult[]
  model_votes?: ModelVote[]
  decision: Decision | null
  reasons: string[]
  created_at: string
}

interface RunPage {
  items: Run[]
  total: number
}

const BASE_URL = '/api/v1/runs'

export function startRun(file: File): Promise<Run> {
  const form = new FormData()
  form.append('file', file)
  return request(BASE_URL, { method: 'POST', body: form })
}

export function listRuns(): Promise<RunPage> {
  return request(`${BASE_URL}?limit=100`)
}

export function getRun(id: string): Promise<Run> {
  return request(`${BASE_URL}/${id}`)
}

export function providePurchaseOrder(id: string, poNumber: string): Promise<Run> {
  return request(`${BASE_URL}/${id}/purchase-order`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ po_number: poNumber }),
  })
}

export function declinePurchaseOrder(id: string): Promise<Run> {
  return request(`${BASE_URL}/${id}/no-purchase-order`, { method: 'POST' })
}

export function deleteRun(id: string): Promise<void> {
  return request(`${BASE_URL}/${id}`, { method: 'DELETE' })
}

const URGENCY: Partial<Record<RunStatus | Decision, number>> = {
  awaiting_po: 0,
  queued: 1,
  running: 1,
  review: 2,
}

/** Whatever needs a person comes first; otherwise the newest stays on top. */
export function sortByUrgency(runs: Run[]): Run[] {
  const rank = (run: Run) => URGENCY[run.decision ?? run.status] ?? 3
  return [...runs].sort((a, b) => rank(a) - rank(b))
}

export function isWorking(status: RunStatus): boolean {
  return status === 'queued' || status === 'running'
}

export function matchesFilter(run: Run, filter: RunFilter): boolean {
  if (filter === 'all') return true
  return filter === 'awaiting_po' ? run.status === 'awaiting_po' : run.decision === filter
}
