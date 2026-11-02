import type { DocumentStatus, PageMethod } from '../api/documents'
import type { Decision, RunStatus } from '../api/runs'

type BadgeValue = DocumentStatus | PageMethod | RunStatus | Decision

const LABELS: Record<BadgeValue, string> = {
  queued: 'Checking',
  processing: 'Checking',
  running: 'Checking',
  completed: 'Read',
  failed: 'Failed',
  native: 'Text layer',
  ocr: 'OCR',
  parse: 'Nemotron Parse',
  blank: 'Blank',
  awaiting_po: 'Needs you',
  accept: 'Accepted',
  review: 'In review',
  reject: 'Rejected',
}

export function StatusBadge({ value }: { value: BadgeValue }) {
  return <span className={`chip chip-${value}`}>{LABELS[value]}</span>
}
