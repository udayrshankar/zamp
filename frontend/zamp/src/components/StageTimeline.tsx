import type { Stage, StageName } from '../api/runs'

const STAGE_LABELS: Record<StageName, string> = {
  extraction: 'Read the document',
  po_detection: 'Found the purchase order',
  po_confirmation: 'Confirmed with you',
  verification: 'Compared invoice and PO',
  checks: 'Ran the rules',
  decision: 'Made a decision',
}

function duration(stage: Stage): string | null {
  if (!stage.started_at || !stage.finished_at) return null
  const seconds = (Date.parse(stage.finished_at) - Date.parse(stage.started_at)) / 1000
  return `${seconds.toFixed(1)}s`
}

export function StageTimeline({ stages }: { stages: Stage[] }) {
  const happened = stages.filter((stage) => stage.summary)

  return (
    <ol className="log">
      {happened.map((stage) => (
        <li key={stage.name}>
          <span className="log-title">{STAGE_LABELS[stage.name]}</span>
          <span className="log-summary">{stage.summary}</span>
          <span className="log-time">{duration(stage)}</span>
        </li>
      ))}
    </ol>
  )
}
