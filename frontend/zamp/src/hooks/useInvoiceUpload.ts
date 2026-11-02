import { useState } from 'react'
import { startRun } from '../api/runs'

export function useInvoiceUpload(onDone: (ids: string[]) => void) {
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const upload = async (files: File[]) => {
    if (files.length === 0) return
    setUploading(true)
    setError(null)
    const ids: string[] = []
    const failures: string[] = []
    for (const file of files) {
      try {
        const { id } = await startRun(file)
        ids.push(id)
      } catch (cause) {
        const reason = cause instanceof Error ? cause.message : 'The upload failed.'
        failures.push(`${file.name}: ${reason}`)
      }
    }
    setUploading(false)
    if (failures.length > 0) setError(failures.join(' '))
    if (ids.length > 0) onDone(ids)
  }

  return { upload, uploading, error }
}
