import { request } from './client'

export type PurchaseOrderFields = Record<string, unknown>

export interface PurchaseOrderData {
  po_number: string
  fields: PurchaseOrderFields
}

export interface PurchaseOrder extends PurchaseOrderData {
  id: string
  created_at: string
  updated_at: string
}

interface PurchaseOrderPage {
  items: PurchaseOrder[]
  total: number
}

const BASE_URL = '/api/v1/purchase-orders'

function sendJson(url: string, method: string, data: PurchaseOrderData): Promise<PurchaseOrder> {
  return request(url, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

const PAGE_SIZE = 100

export async function listAllPurchaseOrders(): Promise<PurchaseOrder[]> {
  const orders: PurchaseOrder[] = []
  let total = 0
  do {
    const page = await request<PurchaseOrderPage>(
      `${BASE_URL}?limit=${PAGE_SIZE}&offset=${orders.length}`,
    )
    orders.push(...page.items)
    total = page.total
    if (page.items.length === 0) break
  } while (orders.length < total)
  return orders
}

export function getPurchaseOrder(id: string): Promise<PurchaseOrder> {
  return request(`${BASE_URL}/${id}`)
}

export function createPurchaseOrder(data: PurchaseOrderData): Promise<PurchaseOrder> {
  return sendJson(BASE_URL, 'POST', data)
}

export function updatePurchaseOrder(id: string, data: PurchaseOrderData): Promise<PurchaseOrder> {
  return sendJson(`${BASE_URL}/${id}`, 'PUT', data)
}

export function deletePurchaseOrder(id: string): Promise<void> {
  return request(`${BASE_URL}/${id}`, { method: 'DELETE' })
}
