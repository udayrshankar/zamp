import { request } from './client'

export type DocumentStatus = 'queued' | 'processing' | 'completed' | 'failed'
export type PageMethod = 'native' | 'ocr' | 'parse' | 'blank' | 'failed'
export type RoutingReason =
  | 'text_layer_ok'
  | 'no_text_layer'
  | 'garbled_text_layer'
  | 'sparse_text_over_image'

export interface ExtractionSummary {
  native_pages: number
  ocr_pages: number
  parse_pages: number
  blank_pages: number
  failed_pages: number
  mean_ocr_confidence: number | null
}

export interface ExtractionWarning {
  code: string
  message: string
  page: number | null
}

export interface DocumentError {
  code: string
  message: string
}

export interface DocumentListItem {
  id: string
  filename: string
  sha256: string
  size_bytes: number
  status: DocumentStatus
  page_count: number | null
  summary: ExtractionSummary | null
  warnings: ExtractionWarning[]
  error: DocumentError | null
  created_at: string
  updated_at: string
}

export interface PageResult {
  number: number
  method: PageMethod
  routing_reason: RoutingReason
  text: string
  confidence: number | null
  gap_filled: boolean
}

export interface DocumentDetail extends DocumentListItem {
  pages: PageResult[]
}

interface DocumentPage {
  items: DocumentListItem[]
  total: number
}

const BASE_URL = '/api/v1/documents'

export function uploadDocument(file: File): Promise<{ id: string }> {
  const form = new FormData()
  form.append('file', file)
  return request(BASE_URL, { method: 'POST', body: form })
}

export function listDocuments(): Promise<DocumentPage> {
  return request(`${BASE_URL}?limit=50`)
}

export function getDocument(id: string): Promise<DocumentDetail> {
  return request(`${BASE_URL}/${id}`)
}

export function documentFileUrl(id: string): string {
  return `${BASE_URL}/${id}/file`
}

export function isFinished(status: DocumentStatus): boolean {
  return status === 'completed' || status === 'failed'
}
