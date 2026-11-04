/**
 * A PO's line items as rows people can type into, and back. Rows are saved with
 * the keys the backend reads (description, qty, unit, unit_price), so a PO
 * entered here is always checked line by line. Other keys on a row, like an
 * HSN code, are kept as they were.
 */

export interface LineRow {
  id: number
  description: string
  quantity: string
  unit: string
  unitPrice: string
  extra: Record<string, unknown>
}

// The same names backend/app/workflow/checks/lines.py looks for.
const DESCRIPTION_KEYS = ['description', 'item', 'name', 'product', 'particulars']
const QUANTITY_KEYS = ['qty', 'quantity', 'qnty', 'units']
const PRICE_KEYS = ['unit_price', 'unit_rate', 'price', 'rate']
const UNIT_KEYS = ['unit', 'uom', 'unit_of_measure', 'units_of_measure', 'measure', 'units']
// Worked out from quantity and price on every save.
const DERIVED_KEYS = ['amount']

export const DEFAULT_LINES_KEY = 'line_items'

export const UNIT_SUGGESTIONS = [
  'nos', 'kg', 'tonne', 'g', 'litre', 'ml', 'metre', 'mm', 'pair', 'dozen', 'box', 'set', 'month',
]

let nextId = 0

export function emptyLine(): LineRow {
  return { id: nextId++, description: '', quantity: '', unit: '', unitPrice: '', extra: {} }
}

const normalise = (key: string) => key.trim().toLowerCase()

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/** "1,24,000.50" or "₹ 62" as a number; null when blank or not a number. */
export function parseNumber(text: string): number | null {
  const cleaned = text.replace(/[,\s₹$€£]/g, '')
  if (!cleaned) return null
  const value = Number(cleaned)
  return Number.isFinite(value) ? value : null
}

function asText(value: unknown): string {
  return typeof value === 'number' || typeof value === 'string' ? String(value) : ''
}

function toRow(source: Record<string, unknown>): LineRow {
  const row = emptyLine()
  for (const [key, value] of Object.entries(source)) {
    const name = normalise(key)
    if (!row.description && typeof value === 'string' && DESCRIPTION_KEYS.some((k) => name.includes(k)) && !UNIT_KEYS.includes(name)) {
      row.description = value
    } else if (!row.quantity && QUANTITY_KEYS.includes(name) && typeof value !== 'string') {
      row.quantity = asText(value)
    } else if (!row.unit && UNIT_KEYS.includes(name) && typeof value === 'string') {
      row.unit = value
    } else if (!row.unitPrice && PRICE_KEYS.includes(name)) {
      row.unitPrice = asText(value)
    } else if (!row.quantity && QUANTITY_KEYS.includes(name)) {
      row.quantity = asText(value)
    } else if (!DERIVED_KEYS.includes(name)) {
      row.extra[key] = value
    }
  }
  return row
}

/** The field holding the PO's line items, if it has one: the first list of rows. */
export function findLineItems(fields: Record<string, unknown>): { key: string; rows: LineRow[] } | null {
  for (const [key, value] of Object.entries(fields)) {
    if (Array.isArray(value) && value.length > 0 && value.every(isRecord)) {
      return { key, rows: value.map(toRow) }
    }
  }
  return null
}

export function lineAmount(row: LineRow): number | null {
  const quantity = parseNumber(row.quantity)
  const price = parseNumber(row.unitPrice)
  if (quantity === null || price === null) return null
  return Math.round(quantity * price * 100) / 100
}

function isBlank(row: LineRow): boolean {
  return !row.description.trim() && !row.quantity.trim() && !row.unit.trim() && !row.unitPrice.trim()
}

/** The rows as saved. Throws with a message naming the line when one can't be. */
export function toLineFields(rows: LineRow[]): Record<string, unknown>[] {
  return rows.filter((row) => !isBlank(row)).map((row, index) => {
    const line = `Line ${index + 1}`
    if (!row.description.trim()) throw new Error(`${line} needs a description.`)
    const quantity = parseNumber(row.quantity)
    if (row.quantity.trim() && quantity === null) throw new Error(`${line}: the quantity must be a number.`)
    const price = parseNumber(row.unitPrice)
    if (row.unitPrice.trim() && price === null) throw new Error(`${line}: the unit price must be a number.`)

    const saved: Record<string, unknown> = { description: row.description.trim() }
    if (quantity !== null) saved.qty = quantity
    if (row.unit.trim()) saved.unit = row.unit.trim()
    if (price !== null) saved.unit_price = price
    const amount = lineAmount(row)
    if (amount !== null) saved.amount = amount
    const kept = Object.entries(row.extra).filter(([key]) => !(normalise(key) in saved))
    return { ...saved, ...Object.fromEntries(kept) }
  })
}
