import { formatAmount } from '../format'
import { emptyLine, lineAmount, UNIT_SUGGESTIONS } from '../lineItems'
import type { LineRow } from '../lineItems'
import { Icon } from './Icon'

interface LineItemsEditorProps {
  lines: LineRow[]
  onChange: (lines: LineRow[]) => void
}

const UNITS_LIST = 'po-unit-suggestions'

export function LineItemsEditor({ lines, onChange }: LineItemsEditorProps) {
  const update = (id: number, change: Partial<LineRow>) =>
    onChange(lines.map((line) => (line.id === id ? { ...line, ...change } : line)))

  const amounts = lines.map(lineAmount)
  const priced = amounts.filter((amount): amount is number => amount !== null)
  const total = priced.length > 0 ? priced.reduce((sum, amount) => sum + amount, 0) : null

  return (
    <section className="po-lines" aria-labelledby="po-lines-title">
      <h2 id="po-lines-title">Line items</h2>
      <p className="hint">
        Each invoice line is matched to one of these by its description, then checked against the
        quantity and unit price. Invoices in another unit of the same kind, like kg against tonnes,
        are converted.
      </p>

      {lines.length > 0 && (
        <div className="po-line po-line-labels" aria-hidden="true">
          <span>Description</span>
          <span className="number">Qty</span>
          <span>Unit</span>
          <span className="number">Unit price</span>
          <span className="number">Amount</span>
          <span />
        </div>
      )}

      {lines.map((line, index) => (
        <div className="po-line" key={line.id} role="group" aria-label={`Line ${index + 1}`}>
          <input
            className="input po-line-description"
            aria-label="Description"
            placeholder="Description, with size or model"
            value={line.description}
            onChange={(event) => update(line.id, { description: event.target.value })}
          />
          <input
            className="input input-number"
            aria-label="Quantity"
            placeholder="Qty"
            inputMode="decimal"
            value={line.quantity}
            onChange={(event) => update(line.id, { quantity: event.target.value })}
          />
          <input
            className="input"
            aria-label="Unit"
            placeholder="nos"
            list={UNITS_LIST}
            value={line.unit}
            onChange={(event) => update(line.id, { unit: event.target.value })}
          />
          <input
            className="input input-number"
            aria-label="Unit price"
            placeholder="Unit price"
            inputMode="decimal"
            value={line.unitPrice}
            onChange={(event) => update(line.id, { unitPrice: event.target.value })}
          />
          <output className="po-line-amount" aria-label="Amount">
            {formatAmount(amounts[index])}
          </output>
          <button
            type="button"
            className="button button-line button-icon"
            aria-label={`Remove line ${index + 1}`}
            onClick={() => onChange(lines.filter((other) => other.id !== line.id))}
          >
            <Icon name="close" />
          </button>
        </div>
      ))}

      <datalist id={UNITS_LIST}>
        {UNIT_SUGGESTIONS.map((unit) => (
          <option key={unit} value={unit} />
        ))}
      </datalist>

      <div className="po-lines-foot">
        <button
          type="button"
          className="button button-line button-small"
          onClick={() => onChange([...lines, emptyLine()])}
        >
          <Icon name="plus" />
          Add line item
        </button>
        {total !== null && (
          <p className="po-lines-total">
            Lines total, before tax <strong>{formatAmount(total)}</strong>
          </p>
        )}
      </div>
    </section>
  )
}
