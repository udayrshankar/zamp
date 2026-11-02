import type { Run } from './api/runs'

function invoiceName(run: Run): string {
  return run.verification?.invoice.invoice_number ?? run.filename
}

function amountSentence(run: Run, name: string, po: string, message: string): string {
  const invoiceTotal = run.verification?.invoice.total
  const poTotal = run.verification?.purchase_order.total
  if (message.includes('earlier')) return `${name} takes ${po} over its limit.`
  if (!poTotal) return `${po} has no total to compare ${name} with.`
  if (!invoiceTotal) return `${name} has no total to compare with ${po}.`
  const percent = Math.round(((invoiceTotal - poTotal) / poTotal) * 100)
  return `${name} is ${percent}% over ${po}.`
}

/** One plain sentence that says what happened, for lists and headlines. */
export function runSentence(run: Run): string {
  const name = invoiceName(run)
  const po = run.po_number ?? 'its PO'

  if (run.status === 'awaiting_po') return `${name} needs a purchase order.`
  if (run.decision === null) return `Checking ${name}.`
  if (run.decision === 'accept') return `${name} matches ${po}.`

  const flagged = [...run.checks]
    .sort((a, b) => Number(b.outcome === 'reject') - Number(a.outcome === 'reject'))
    .find((check) => check.outcome !== 'pass')
  if (!flagged) return run.reasons[0] ?? `${name} needs a person to look at it.`

  const sentences: Record<string, string> = {
    po_amount: amountSentence(run, name, po, flagged.message),
    duplicate: `${name} was already processed.`,
    vendor:
      flagged.outcome === 'reject'
        ? `${name} is from a different vendor than ${po}.`
        : `The vendor on ${name} may not match ${po}.`,
    required_fields: `${name} is missing required details.`,
    reading_accuracy: `Some amounts on ${name} couldn't be confirmed.`,
    arithmetic: `The numbers on ${name} don't add up.`,
    currency: `${name} is in a different currency from ${po}.`,
    extraction_quality: `${name} was hard to read.`,
    reported_discrepancies: `${name} has items that aren't on ${po}.`,
  }
  return sentences[flagged.name] ?? flagged.message
}
