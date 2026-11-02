import type { CheckResult, Run } from '../api/runs'
import { formatAmount } from '../format'
import { DocumentDetail } from './DocumentDetail'
import { Icon } from './Icon'
import { StageTimeline } from './StageTimeline'

const CHECK_LABELS: Record<string, string> = {
  required_fields: 'Required fields',
  reading_accuracy: 'Reading accuracy',
  arithmetic: 'Arithmetic',
  duplicate: 'Duplicate',
  vendor: 'Vendor',
  currency: 'Currency',
  po_amount: 'Amount against PO',
  extraction_quality: 'Document quality',
  reported_discrepancies: 'Line items',
}

const OUTCOME_LABELS: Record<CheckResult['outcome'], string> = {
  pass: 'Passed',
  review: 'Review',
  reject: 'Failed',
}

function Checks({ checks }: { checks: CheckResult[] }) {
  if (checks.length === 0) return null
  const flaggedFirst = [...checks].sort(
    (a, b) => Number(a.outcome === 'pass') - Number(b.outcome === 'pass'),
  )

  return (
    <section>
      <h3>Checks</h3>
      <table className="table">
        <tbody>
          {flaggedFirst.map((check) => (
            <tr key={check.name}>
              <td className="table-name">{CHECK_LABELS[check.name] ?? check.name}</td>
              <td className={`table-outcome outcome-${check.outcome}`}>
                {OUTCOME_LABELS[check.outcome]}
              </td>
              <td className="table-muted">{check.message}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}

function LineItems({ run }: { run: Run }) {
  const invoice = run.verification?.invoice
  if (!invoice || invoice.line_items.length === 0) return null

  return (
    <section>
      <h3>Line items</h3>
      <table className="table">
        <thead>
          <tr>
            <th>Description</th>
            <th className="number">Qty</th>
            <th className="number">Unit price</th>
            <th className="number">Amount</th>
          </tr>
        </thead>
        <tbody>
          {invoice.line_items.map((item, index) => (
            <tr key={index}>
              <td>{item.description}</td>
              <td className="number">{item.quantity ?? '—'}</td>
              <td className="number">{formatAmount(item.unit_price)}</td>
              <td className="number">{formatAmount(item.amount)}</td>
            </tr>
          ))}
          {invoice.tax !== null && (
            <tr>
              <td colSpan={3}>Tax</td>
              <td className="number">{formatAmount(invoice.tax)}</td>
            </tr>
          )}
          {invoice.charges.map((charge) => (
            <tr key={charge.label}>
              <td colSpan={3}>{charge.label}</td>
              <td className="number">{formatAmount(charge.amount)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}

export function RunWhy({ run }: { run: Run }) {
  return (
    <details className="why">
      <summary>
        See why
        <Icon name="chevron" />
      </summary>
      <div className="why-body">
        <Checks checks={run.checks} />
        <LineItems run={run} />
        <section>
          <h3>What happened</h3>
          <StageTimeline stages={run.stages} />
        </section>
        <section>
          <h3>Extracted text</h3>
          <DocumentDetail key={run.status} id={run.document_id} />
        </section>
      </div>
    </details>
  )
}
