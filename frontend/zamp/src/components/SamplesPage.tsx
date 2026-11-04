import { useState } from 'react'
import { SAMPLE_COUNT, SAMPLE_GROUPS, SAMPLES_ZIP, sampleUrl } from '../samples'
import type { Sample, SampleGroup } from '../samples'
import { Icon } from './Icon'
import { StatusBadge } from './StatusBadge'

interface SamplesPageProps {
  uploading: boolean
  onFiles: (files: File[]) => void
}

interface SampleRowProps {
  folder: SampleGroup['folder']
  sample: Sample
  busy: boolean
  disabled: boolean
  onCheck: () => void
}

function SampleRow({ folder, sample, busy, disabled, onCheck }: SampleRowProps) {
  const url = sampleUrl(folder, sample.file)
  return (
    <li className="sample">
      <div className="sample-text">
        <span className="sample-tests">{sample.tests}</span>
        <span className="sample-meta">
          {sample.file} · {sample.quality}
        </span>
        {sample.note && <span className="sample-note">{sample.note}</span>}
      </div>
      <StatusBadge value={sample.expected} />
      <div className="sample-actions">
        <button type="button" className="button button-line button-small" disabled={disabled} onClick={onCheck}>
          {busy ? 'Uploading' : 'Check it'}
        </button>
        <a className="icon-link" href={url} download aria-label={`Download ${sample.file}`} title="Download">
          <Icon name="download" />
        </a>
      </div>
    </li>
  )
}

export function SamplesPage({ uploading, onFiles }: SamplesPageProps) {
  const [checking, setChecking] = useState<string | null>(null)
  const [fetching, setFetching] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const busy = fetching || uploading

  // Fetches the sample and hands it to the same upload path as a dropped file.
  const check = async (folder: SampleGroup['folder'], file: string) => {
    setChecking(file)
    setFetching(true)
    setError(null)
    try {
      const response = await fetch(sampleUrl(folder, file))
      if (!response.ok) throw new Error(`Request failed (${response.status})`)
      const blob = await response.blob()
      onFiles([new File([blob], file, { type: 'application/pdf' })])
    } catch (cause) {
      setError(`${file} couldn't be loaded. ${cause instanceof Error ? cause.message : ''}`)
    } finally {
      setFetching(false)
    }
  }

  return (
    <>
      <header className="page-head">
        <div>
          <h1>Test invoices</h1>
          <p className="lead">
            {SAMPLE_COUNT} invoices billed to IIT Madras. Their purchase orders are already on file, and each
            one shows the result it should get.
          </p>
        </div>
        <a className="button button-solid" href={SAMPLES_ZIP} download>
          <Icon name="download" />
          Download all
        </a>
      </header>

      <ol className="steps" aria-label="How to test">
        <li>
          <strong>Run one</strong>
          <span>Press Check it, or drop a downloaded PDF anywhere.</span>
        </li>
        <li>
          <strong>Keep the order</strong>
          <span>Accepted set first. Two problem invoices build on earlier ones.</span>
        </li>
        <li>
          <strong>Compare</strong>
          <span>Each row shows the result it should get.</span>
        </li>
      </ol>

      {error && (
        <p className="alert" role="alert">
          {error}
        </p>
      )}

      {SAMPLE_GROUPS.map((group) => (
        <section key={group.folder} className="sample-group" aria-labelledby={`samples-${group.folder}`}>
          <h2 id={`samples-${group.folder}`}>{group.title}</h2>
          <p className="hint">{group.summary}</p>
          <ol className="samples">
            {group.samples.map((sample) => (
              <SampleRow
                key={sample.file}
                folder={group.folder}
                sample={sample}
                busy={busy && checking === sample.file}
                disabled={busy}
                onCheck={() => void check(group.folder, sample.file)}
              />
            ))}
          </ol>
        </section>
      ))}
    </>
  )
}
