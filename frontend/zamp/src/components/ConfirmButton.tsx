import { useState } from 'react'

interface ConfirmButtonProps {
  label: string
  question: string
  disabled?: boolean
  onConfirm: () => void
}

/** A destructive action that asks in place, so it can't be hit by accident. */
export function ConfirmButton({ label, question, disabled, onConfirm }: ConfirmButtonProps) {
  const [asking, setAsking] = useState(false)

  if (!asking) {
    return (
      <button
        type="button"
        className="button button-line"
        disabled={disabled}
        onClick={() => setAsking(true)}
      >
        {label}
      </button>
    )
  }

  return (
    <span className="confirm">
      <span>{question}</span>
      <button type="button" className="button button-danger" onClick={onConfirm}>
        {label}
      </button>
      <button type="button" className="button button-line" onClick={() => setAsking(false)}>
        Cancel
      </button>
    </span>
  )
}
