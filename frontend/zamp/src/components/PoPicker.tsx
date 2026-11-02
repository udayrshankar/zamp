import { useState } from 'react'
import type { FormEvent } from 'react'
import { listAllPurchaseOrders } from '../api/purchaseOrders'
import { declinePurchaseOrder, providePurchaseOrder } from '../api/runs'
import type { Run } from '../api/runs'
import { usePolling } from '../hooks/usePolling'
import { matchPoNumbers, poSubtitle } from '../poSearch'

interface PoPickerProps {
  run: Run
  onAnswered: () => void
}

const MAX_SHOWN = 6
const neverPoll = () => false

export function PoPicker({ run, onAnswered }: PoPickerProps) {
  const { data } = usePolling(listAllPurchaseOrders, neverPoll)
  const [typed, setTyped] = useState('')
  const [error, setError] = useState<string | null>(null)

  const orders = data ?? []
  const suggested = orders.filter((order) => run.po_suggestions.includes(order.po_number))
  const matches = typed.trim() || suggested.length === 0 ? matchPoNumbers(orders, typed) : suggested

  const send = async (answer: () => Promise<unknown>) => {
    setError(null)
    try {
      await answer()
      onAnswered()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'That answer could not be saved. Try again.')
    }
  }

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    const poNumber = matches.length === 1 ? matches[0].po_number : typed.trim()
    if (poNumber) void send(() => providePurchaseOrder(run.id, poNumber))
  }

  return (
    <form className="question" onSubmit={handleSubmit}>
      <h1>Which purchase order is this for?</h1>
      <p className="lead">{run.po_prompt}</p>

      <label className="field">
        PO number
        <input
          className="input"
          autoComplete="off"
          placeholder="Start typing"
          value={typed}
          onChange={(event) => setTyped(event.target.value)}
        />
      </label>

      {matches.length > 0 ? (
        <ul className="options">
          {matches.slice(0, MAX_SHOWN).map((order) => (
            <li key={order.id}>
              <button
                type="button"
                className="option"
                aria-pressed={typed === order.po_number}
                onClick={() => setTyped(order.po_number)}
              >
                <strong>{order.po_number}</strong>
                <span>{poSubtitle(order)}</span>
              </button>
            </li>
          ))}
        </ul>
      ) : (
        data && <p className="hint">No purchase orders match that number.</p>
      )}
      {matches.length > MAX_SHOWN && (
        <p className="hint">
          Showing {MAX_SHOWN} of {matches.length}. Keep typing to narrow it down.
        </p>
      )}

      <div className="actions">
        <button type="submit" className="button button-solid" disabled={!typed.trim()}>
          Continue
        </button>
        <button
          type="button"
          className="button button-line"
          onClick={() => void send(() => declinePurchaseOrder(run.id))}
        >
          There is no PO
        </button>
      </div>

      {error && (
        <p className="alert" role="alert">
          {error}
        </p>
      )}
    </form>
  )
}
