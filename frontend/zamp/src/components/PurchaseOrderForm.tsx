import { useState } from 'react'
import type { FormEvent } from 'react'
import {
  createPurchaseOrder,
  deletePurchaseOrder,
  updatePurchaseOrder,
} from '../api/purchaseOrders'
import type { PurchaseOrder, PurchaseOrderFields } from '../api/purchaseOrders'
import { ConfirmButton } from './ConfirmButton'

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

function toRows(fields: PurchaseOrderFields): FieldRow[] {
  return Object.entries(fields).map(([name, value]) => ({
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

function toFields(rows: FieldRow[]): PurchaseOrderFields {
  const named = rows.filter((row) => row.name.trim())
  const names = named.map((row) => row.name.trim())
  if (new Set(names).size !== names.length) {
    throw new Error('Each field name can only be used once.')
  }
  return Object.fromEntries(named.map((row) => [row.name.trim(), parseValue(row.value)]))
}

export function PurchaseOrderForm({ order, onSaved, onDeleted }: PurchaseOrderFormProps) {
  const [poNumber, setPoNumber] = useState(order?.po_number ?? '')
  const [rows, setRows] = useState<FieldRow[]>(() => toRows(order?.fields ?? {}))
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
      const data = { po_number: poNumber, fields: toFields(rows) }
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
          Add what this PO needs, like vendor, total or handling charges.
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
      </div>

      <div className="actions">
        <button
          type="button"
          className="button button-line"
          onClick={() => setRows([...rows, EMPTY_ROW])}
        >
          Add field
        </button>
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
