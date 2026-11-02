import { useCallback } from 'react'
import { getRun, isWorking, listRuns } from '../api/runs'
import type { Run } from '../api/runs'
import { usePolling } from './usePolling'

type RunPage = Awaited<ReturnType<typeof listRuns>>

const hasWorkingRuns = (page: RunPage) => page.items.some((run) => isWorking(run.status))
const isRunWorking = (run: Run) => isWorking(run.status)

export function useRuns() {
  const { data, error, refresh } = usePolling(listRuns, hasWorkingRuns)
  return { runs: data?.items ?? [], loaded: data !== null, error, refresh }
}

export function useRun(id: string) {
  const load = useCallback(() => getRun(id), [id])
  const { data, error, refresh } = usePolling(load, isRunWorking)
  return { run: data, error, refresh }
}
