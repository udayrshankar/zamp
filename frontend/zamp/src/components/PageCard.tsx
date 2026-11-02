import type { PageResult, RoutingReason } from '../api/documents'
import { StatusBadge } from './StatusBadge'

const ROUTING_EXPLANATIONS: Record<RoutingReason, string> = {
  text_layer_ok: 'The embedded text looked reliable.',
  no_text_layer: 'Almost no embedded text, so the page was read from its image.',
  garbled_text_layer: 'The embedded text was garbled, so the page was read from its image.',
  sparse_text_over_image: 'Mostly an image with little text, so the page was read from its image.',
}

export function PageCard({ page }: { page: PageResult }) {
  return (
    <article className="page-card">
      <header>
        <h3>Page {page.number}</h3>
        <StatusBadge value={page.method} />
        {page.confidence !== null && (
          <span className="page-confidence">{Math.round(page.confidence * 100)}% confidence</span>
        )}
      </header>
      <p className="page-reason">
        {ROUTING_EXPLANATIONS[page.routing_reason]}
        {page.gap_filled && ' Nemotron Parse missed some amounts, so OCR added them.'}
      </p>
      {page.text && <pre>{page.text}</pre>}
    </article>
  )
}
