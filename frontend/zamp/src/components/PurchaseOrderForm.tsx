import { useState } from 'react'
import type { FormEvent } from 'react'
import {
  createPurchaseOrder,
  deletePurchaseOrder,
  updatePurchaseOrder,
} from '../api/purchaseOrders'
import type { PurchaseOrder, PurchaseOrderFields } from '../api/purchaseOrders'
import { DEFAULT_LINES_KEY, emptyLine, findLineItems, toLineFields } from '../lineItems'
import type { LineRow } from '../lineItems'
import { ConfirmButton } from './ConfirmButton'
import { Icon } from './Icon'
import { LineItemsEditor } from './LineItemsEditor'

interface PurchaseOrderFormProps {
  order: PurchaseOrder | null
  onSaved: (order: PurchaseOrder) => void
  onDeleted: () => void
}

interface FieldRow {
  name: string
  value: string
}

const EMPTY_ROW: FieldRow = { name: '', value: '' }

function toRows(fields: PurchaseOrderFields, linesKey: string): FieldRow[] {
  return Object.entries(fields)
    .filter(([name]) => name !== linesKey)
    .map(([name, value]) => ({
    name,
    value: typeof value === 'string' ? value : JSON.stringify(value),
  }))
}

/** Numbers, booleans, lists and objects typed as JSON keep their type. */
function parseValue(value: string): unknown {
  try {
    return JSON.parse(value)
  } catch {
    return value
  }
}

function toFields(rows: FieldRow[], lines: LineRow[], linesKey: string): PurchaseOrderFields {
  const named = rows.filter((row) => row.name.trim())
  const names = named.map((row) => row.name.trim())
  if (new Set(names).size !== names.length) {
    throw new Error('Each field name can only be used once.')
  }
  if (names.includes(linesKey)) {
    throw new Error(`"${linesKey}" holds the line items, so pick another field name.`)
  }
  const fields = Object.fromEntries(named.map((row) => [row.name.trim(), parseValue(row.value)]))
  const lineFields = toLineFields(lines)
  return lineFields.length > 0 ? { ...fields, [linesKey]: lineFields } : fields
}

export function PurchaseOrderForm({ order, onSaved, onDeleted }: PurchaseOrderFormProps) {
  const [poNumber, setPoNumber] = useState(order?.po_number ?? '')
  const [found] = useState(() => findLineItems(order?.fields ?? {}))
  const linesKey = found?.key ?? DEFAULT_LINES_KEY
  const [rows, setRows] = useState<FieldRow[]>(() => toRows(order?.fields ?? {}, linesKey))
  // A new PO starts with one empty line to fill in; blank lines aren't saved.
  const [lines, setLines] = useState<LineRow[]>(() => found?.rows ?? (order ? [] : [emptyLine()]))
  const [error, setError] = useState<string | null>(null)

  const updateRow = (index: number, change: Partial<FieldRow>) => {
    setRows(rows.map((row, i) => (i === index ? { ...row, ...change } : row)))
  }

  const run = async (action: () => Promise<void>) => {
    setError(null)
    try {
      await action()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Something went wrong.')
    }
  }

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    void run(async () => {
      const data = { po_number: poNumber, fields: toFields(rows, lines, linesKey) }
      onSaved(
        await (order ? updatePurchaseOrder(order.id, data) : createPurchaseOrder(data)),
      )
    })
  }

  const handleDelete = () => {
    if (!order) return
    void run(async () => {
      await deletePurchaseOrder(order.id)
      onDeleted()
    })
  }

  return (
    <form className="po-form" onSubmit={handleSubmit}>
      <h1>{order ? `Edit ${order.po_number}` : 'Add a purchase order'}</h1>

      <label className="field">
        PO number
        <input
          className="input"
          name="po_number"
          required
          value={poNumber}
          onChange={(event) => setPoNumber(event.target.value)}
        />
      </label>

      <div className="po-fields">
        <h2>Details</h2>
        <p className="hint">
          Add what this PO needs, like vendor, total, currency or handling charges.
        </p>
        {rows.map((row, index) => (
          <div className="po-row" key={index}>
            <input
              className="input"
              aria-label="Field name"
              placeholder="Field name"
              value={row.name}
              onChange={(event) => updateRow(index, { name: event.target.value })}
            />
            <input
              className="input"
              aria-label="Field value"
              placeholder="Value"
              value={row.value}
              onChange={(event) => updateRow(index, { value: event.target.value })}
            />
            <button
              type="button"
              className="button button-line"
              onClick={() => setRows(rows.filter((_, i) => i !== index))}
            >
              Remove
            </button>
          </div>
        ))}
        <button
          type="button"
          className="button button-line button-small po-add"
          onClick={() => setRows([...rows, EMPTY_ROW])}
        >
          <Icon name="plus" />
          Add field
        </button>
      </div>

      <LineItemsEditor lines={lines} onChange={setLines} />

      <div className="actions">
        <button type="submit" className="button button-solid">
          {order ? 'Save changes' : 'Add purchase order'}
        </button>
        {order && (
          <ConfirmButton
            label="Delete"
            question={`Delete ${order.po_number}?`}
            onConfirm={handleDelete}
          />
        )}
      </div>

      {error && (
        <p className="alert" role="alert">
          {error}
        </p>
      )}
    </form>
  )
}
