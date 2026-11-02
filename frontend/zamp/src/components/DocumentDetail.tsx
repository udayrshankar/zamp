import { isFinished } from '../api/documents'
import { useDocument } from '../hooks/useDocuments'
import { PageCard } from './PageCard'

export function DocumentDetail({ id }: { id: string }) {
  const { document, error } = useDocument(id)

  if (!document) {
    return error ? (
      <p className="message message-error">{error}</p>
    ) : (
      <p className="empty">Loading…</p>
    )
  }

  const { summary } = document

  return (
    <section className="detail">
      {!isFinished(document.status) && (
        <p className="empty">Reading the document. This updates automatically.</p>
      )}

      {document.error && (
        <p className="message message-error">
          {document.error.message} <code>{document.error.code}</code>
        </p>
      )}

      {summary && (
        <dl className="summary">
          <div>
            <dt>Pages</dt>
            <dd>{document.page_count}</dd>
          </div>
          <div>
            <dt>Text layer</dt>
            <dd>{summary.native_pages}</dd>
          </div>
          <div>
            <dt>Nemotron Parse</dt>
            <dd>{summary.parse_pages}</dd>
          </div>
          <div>
            <dt>OCR</dt>
            <dd>{summary.ocr_pages}</dd>
          </div>
          <div>
            <dt>OCR confidence</dt>
            <dd>
              {summary.mean_ocr_confidence === null
                ? '—'
                : `${Math.round(summary.mean_ocr_confidence * 100)}%`}
            </dd>
          </div>
        </dl>
      )}

      {document.warnings.map((warning) => (
        <p key={`${warning.code}-${warning.page}`} className="message message-warning">
          {warning.message}
        </p>
      ))}

      {document.pages.map((page) => (
        <PageCard key={page.number} page={page} />
      ))}
    </section>
  )
}
