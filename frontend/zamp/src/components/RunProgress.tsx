import type { Run, Stage, StageName } from '../api/runs'
import { Icon } from './Icon'

type StepState = 'pending' | 'running' | 'waiting' | 'done' | 'failed'

const STEPS: { label: string; stages: StageName[] }[] = [
  { label: 'Read', stages: ['extraction'] },
  { label: 'Find PO', stages: ['po_detection', 'po_confirmation'] },
  { label: 'Compare', stages: ['verification'] },
  { label: 'Decide', stages: ['checks', 'decision'] },
]

const STATE_LABELS: Record<StepState, string> = {
  pending: 'not started',
  running: 'in progress',
  waiting: 'needs you',
  done: 'done',
  failed: 'could not finish',
}

function stepState(stages: Stage[]): StepState {
  const statuses = stages.map((stage) => stage.status)
  if (statuses.includes('waiting')) return 'waiting'
  if (statuses.includes('running')) return 'running'
  // A failed PO lookup that you then answered is finished, not failed.
  if (statuses.includes('completed')) {
    return statuses.includes('pending') ? 'running' : 'done'
  }
  return statuses.includes('failed') ? 'failed' : 'pending'
}

export function RunProgress({ run }: { run: Run }) {
  return (
    <ol className="steps">
      {STEPS.map(({ label, stages }) => {
        const state = stepState(run.stages.filter((stage) => stages.includes(stage.name)))
        return (
          <li key={label} className={`step step-${state}`}>
            <span className="step-rule" aria-hidden="true" />
            <span className="step-label">
              {state === 'done' && <Icon name="check" />}
              {label}
              <span className="visually-hidden">, {STATE_LABELS[state]}</span>
            </span>
          </li>
        )
      })}
    </ol>
  )
}
