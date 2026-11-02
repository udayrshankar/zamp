import type { PurchaseOrder } from './api/purchaseOrders'

function normalise(value: string): string {
  return value.toUpperCase().replace(/[^A-Z0-9]/g, '')
}

/** Orders whose number contains what's been typed, so "501" finds PO-50101. */
export function matchPoNumbers(orders: PurchaseOrder[], typed: string): PurchaseOrder[] {
  const wanted = normalise(typed)
  return orders.filter((order) => normalise(order.po_number).includes(wanted))
}

/** The first text field on a PO, usually its vendor, for showing in a list. */
export function poSubtitle(order: PurchaseOrder): string {
  const first = Object.values(order.fields).find((value) => typeof value === 'string')
  const count = Object.keys(order.fields).length
  return typeof first === 'string' ? first : `${count} field${count === 1 ? '' : 's'}`
}
