import type { Run } from '../api/runs'
import { formatAmount } from '../format'

function isFlagged(run: Run, checkName: string): boolean {
  return run.checks.some((check) => check.name === checkName && check.outcome !== 'pass')
}

interface RowProps {
  label: string
  invoice: string
  purchaseOrder: string
  flagged?: boolean
}

function Row({ label, invoice, purchaseOrder, flagged }: RowProps) {
  return (
    <tr className={flagged ? 'row-flagged' : undefined}>
      <th scope="row">{label}</th>
      <td>{invoice}</td>
      <td>{purchaseOrder}</td>
      <td className="row-note">{flagged && 'Check this'}</td>
    </tr>
  )
}

export function RunComparison({ run }: { run: Run }) {
  if (!run.verification) return null
  const { invoice, purchase_order: po } = run.verification

  return (
    <table className="compare">
      <thead>
        <tr>
          <td />
          <th scope="col">Invoice</th>
          <th scope="col">Purchase order</th>
          <td />
        </tr>
      </thead>
      <tbody>
        <Row
          label="Number"
          invoice={invoice.invoice_number ?? '—'}
          purchaseOrder={run.po_number ?? '—'}
        />
        <Row
          label="Vendor"
          invoice={invoice.vendor ?? '—'}
          purchaseOrder={po.vendor ?? '—'}
          flagged={isFlagged(run, 'vendor')}
        />
        <Row
          label="Total"
          invoice={formatAmount(invoice.total, invoice.currency)}
          purchaseOrder={formatAmount(po.total, po.currency)}
          flagged={isFlagged(run, 'po_amount')}
        />
      </tbody>
    </table>
  )
}
