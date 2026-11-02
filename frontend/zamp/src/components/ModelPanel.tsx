import type { ModelVote } from '../api/runs'
import { formatAmount, modelName } from '../format'
import { StatusBadge } from './StatusBadge'

const VENDOR_LABELS: Record<NonNullable<ModelVote['vendor_match']>, string> = {
  yes: 'Matches',
  no: 'Different',
  unclear: 'Unsure',
}

function summary(votes: ModelVote[]): string {
  const answered = votes.filter((vote) => vote.status === 'answered')
  if (answered.length === 0) return 'No model could read this invoice.'
  const decisions = new Set(answered.map((vote) => vote.decision))
  const count = `${answered.length} of ${votes.length} model${votes.length === 1 ? '' : 's'} read it`
  return decisions.size === 1
    ? `${count}, and each reading leads to the same decision.`
    : `${count}. Their readings lead to different decisions, so the best-supported reading was used.`
}

export function ModelPanel({ votes }: { votes: ModelVote[] | undefined }) {
  if (!votes || votes.length === 0) return null

  return (
    <section>
      <h3>AI models</h3>
      <p className="hint">{summary(votes)}</p>
      <table className="table">
        <thead>
          <tr>
            <th>Model</th>
            <th>Read</th>
            <th className="number">Invoice no.</th>
            <th className="number">Total</th>
            <th>Vendor</th>
            <th>Would decide</th>
          </tr>
        </thead>
        <tbody>
          {votes.map((vote) => (
            <tr key={vote.model} className={vote.chosen ? 'vote-chosen' : undefined}>
              <td className="table-name">
                {modelName(vote.model)}
                {vote.chosen && <span className="vote-used">Used</span>}
              </td>
              <td className="table-muted">
                {vote.status === 'answered' ? `${vote.seconds.toFixed(1)} s` : (vote.error ?? 'Failed')}
              </td>
              <td className="number">{vote.invoice_number ?? '—'}</td>
              <td className="number">{formatAmount(vote.total)}</td>
              <td>{vote.vendor_match ? VENDOR_LABELS[vote.vendor_match] : '—'}</td>
              <td>{vote.decision ? <StatusBadge value={vote.decision} /> : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}
