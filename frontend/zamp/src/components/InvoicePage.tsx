import { useState } from 'react'
import { documentFileUrl } from '../api/documents'
import { deleteRun, isWorking } from '../api/runs'
import type { Decision, Run, StageName } from '../api/runs'
import { navigate } from '../hooks/useHashRoute'
import { useRun } from '../hooks/useRuns'
import { runSentence } from '../runSentence'
import posthog, { isPostHogEnabled } from '../posthog'
import { ConfirmButton } from './ConfirmButton'
import { Icon } from './Icon'
import { PoPicker } from './PoPicker'
import { RunProgress } from './RunProgress'
import { RunComparison } from './RunResult'
import { RunWhy } from './RunWhy'

const DECISION_WORDS: Record<Decision, string> = {
  accept: 'Accepted.',
  review: 'Needs review.',
  reject: 'Rejected.',
}

const ACTIVITY: Record<StageName, string> = {
  extraction: 'Reading the invoice.',
  po_detection: 'Looking for the purchase order.',
  po_confirmation: 'Looking for the purchase order.',
  verification: 'Comparing it with the purchase order.',
  checks: 'Running the checks.',
  decision: 'Making a decision.',
}

function currentActivity(run: Run): string {
  const stage = run.stages.find(({ status }) => status === 'running')
  return stage ? ACTIVITY[stage.name] : 'Getting started.'
}

export function InvoicePage({ id }: { id: string }) {
  const { run, error, refresh } = useRun(id)
  const [deleteError, setDeleteError] = useState<string | null>(null)
  const [watched, setWatched] = useState(false)

  // The verdict only animates if you saw it arrive, not when reopening an old one.
  if (run && isWorking(run.status) && !watched) setWatched(true)

  const back = (
    <a className="back" href="#/">
      <Icon name="back" />
      Invoices
    </a>
  )

  if (!run) {
    return (
      <>
        {back}
        {error ? <p className="alert">This invoice couldn't be loaded. {error}</p> : null}
      </>
    )
  }

  const handleDelete = async () => {
    setDeleteError(null)
    try {
      await deleteRun(run.id)
      if (isPostHogEnabled) posthog.capture('invoice_deleted')
      navigate('/')
    } catch (cause) {
      setDeleteError(cause instanceof Error ? cause.message : 'This upload could not be deleted.')
    }
  }

  const working = isWorking(run.status)

  return (
    <article className="invoice">
      <header className="invoice-top">
        {back}
        <a
          className="button button-line"
          href={documentFileUrl(run.document_id)}
          target="_blank"
          rel="noreferrer"
        >
          Open PDF
        </a>
      </header>

      <RunProgress run={run} />

      {working && (
        <h1 className="verdict verdict-quiet" key={currentActivity(run)} role="status">
          {currentActivity(run)}
        </h1>
      )}

      {run.status === 'awaiting_po' && <PoPicker key={run.id} run={run} onAnswered={refresh} />}

      {run.decision && (
        <div className={watched ? 'verdict-block verdict-arrive' : 'verdict-block'}>
          <h1 className="verdict">
            <span className={`verdict-word verdict-${run.decision}`}>
              {DECISION_WORDS[run.decision]}
            </span>{' '}
            {runSentence(run)}
          </h1>
          {run.reasons.length > 0 && run.decision !== 'accept' && (
            <ul className="reasons">
              {run.reasons.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      <p className="invoice-file">{run.filename}</p>

      {run.decision && (
        <>
          <RunComparison run={run} />
          <RunWhy run={run} />
        </>
      )}

      {deleteError && (
        <p className="alert" role="alert">
          {deleteError}
        </p>
      )}

      <footer className="actions actions-spread">
        {run.decision ? (
          <a className="button button-solid" href="#/">
            Check another invoice
          </a>
        ) : (
          <span />
        )}
        <ConfirmButton
          label="Delete"
          question="Delete this upload?"
          disabled={working}
          onConfirm={() => void handleDelete()}
        />
      </footer>
    </article>
  )
}
