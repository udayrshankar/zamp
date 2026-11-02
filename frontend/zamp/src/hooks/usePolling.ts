import { useCallback, useEffect, useState } from 'react'

const POLL_INTERVAL_MS = 1500

interface Polling<T> {
  data: T | null
  error: string | null
  refresh: () => void
}

/**
 * Calls `load` immediately, then repeats while `keepPolling` says work is in
 * progress. A failed request keeps retrying so a backend restart recovers by
 * itself. Both callbacks must be stable between renders.
 */
export function usePolling<T>(
  load: () => Promise<T>,
  keepPolling: (data: T) => boolean,
): Polling<T> {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [version, setVersion] = useState(0)

  useEffect(() => {
    let cancelled = false
    let timer: ReturnType<typeof setTimeout>

    const tick = async () => {
      try {
        const next = await load()
        if (cancelled) return
        setData(next)
        setError(null)
        if (keepPolling(next)) timer = setTimeout(tick, POLL_INTERVAL_MS)
      } catch (cause) {
        if (cancelled) return
        setError(cause instanceof Error ? cause.message : 'Something went wrong.')
        timer = setTimeout(tick, POLL_INTERVAL_MS)
      }
    }

    void tick()
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [load, keepPolling, version])

  const refresh = useCallback(() => setVersion((current) => current + 1), [])
  return { data, error, refresh }
}
