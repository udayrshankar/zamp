import { useState } from 'react'
import { matchesFilter, sortByUrgency } from '../api/runs'
import type { Run, RunFilter } from '../api/runs'
import { useRuns } from '../hooks/useRuns'
import { runSentence } from '../runSentence'
import { SAMPLE_COUNT, SAMPLES_ZIP } from '../samples'
import { FilePicker } from './FilePicker'
import { StatusBadge } from './StatusBadge'

interface HomePageProps {
  uploading: boolean
  onFiles: (files: File[]) => void
}

const FILTERS: { key: RunFilter; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'awaiting_po', label: 'Needs you' },
  { key: 'review', label: 'In review' },
  { key: 'accept', label: 'Accepted' },
  { key: 'reject', label: 'Rejected' },
]

const TIME_FORMAT = new Intl.DateTimeFormat(undefined, { day: 'numeric', month: 'short' })

function RunRow({ run }: { run: Run }) {
  return (
    <li>
      <a className="row" href={`#/invoices/${run.id}`}>
        <StatusBadge value={run.decision ?? run.status} />
        <span className="row-sentence">{runSentence(run)}</span>
        <span className="row-date">{TIME_FORMAT.format(new Date(run.created_at))}</span>
      </a>
    </li>
  )
}

export function HomePage({ uploading, onFiles }: HomePageProps) {
  const { runs, loaded, error } = useRuns()
  const [filter, setFilter] = useState<RunFilter>('all')

  const firstVisit = loaded && runs.length === 0
  const visible = sortByUrgency(runs.filter((run) => matchesFilter(run, filter)))

  return (
    <>
      <section className={firstVisit ? 'hero hero-first' : 'hero'}>
        <h1>Drop an invoice.</h1>
        <p className="lead">We'll find its purchase order, compare them and tell you what to do.</p>
        <FilePicker className="button button-solid button-large" disabled={uploading} onFiles={onFiles}>
          {uploading ? 'Uploading' : 'Choose a PDF'}
        </FilePicker>
        <p className="hero-aside">
          No invoice to hand? <a href="#/samples">Try one of {SAMPLE_COUNT} test invoices</a>, or{' '}
          <a href={SAMPLES_ZIP} download>
            download them all
          </a>
          .
        </p>
      </section>

      {error && (
        <p className="alert" role="alert">
          The list couldn't be loaded. {error}
        </p>
      )}

      {runs.length > 0 && (
        <section aria-label="Invoices">
          <nav className="filters" aria-label="Filter invoices">
            {FILTERS.map(({ key, label }) => (
              <button
                key={key}
                type="button"
                aria-pressed={filter === key}
                onClick={() => setFilter(key)}
              >
                {label}
                <span>{runs.filter((run) => matchesFilter(run, key)).length}</span>
              </button>
            ))}
          </nav>
          {visible.length > 0 ? (
            <ul className="rows">
              {visible.map((run) => (
                <RunRow key={run.id} run={run} />
              ))}
            </ul>
          ) : (
            <p className="hint">No invoices here right now.</p>
          )}
        </section>
      )}
    </>
  )
}
