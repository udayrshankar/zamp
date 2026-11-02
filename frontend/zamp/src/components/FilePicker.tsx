import type { ChangeEvent, ReactNode } from 'react'

interface FilePickerProps {
  className: string
  disabled: boolean
  onFiles: (files: File[]) => void
  children: ReactNode
}

export function FilePicker({ className, disabled, onFiles, children }: FilePickerProps) {
  const handleChange = (event: ChangeEvent<HTMLInputElement>) => {
    onFiles([...(event.target.files ?? [])])
    event.target.value = ''
  }

  return (
    <label className={className}>
      <input
        type="file"
        className="visually-hidden"
        accept="application/pdf,.pdf"
        multiple
        disabled={disabled}
        onChange={handleChange}
      />
      {children}
    </label>
  )
}
