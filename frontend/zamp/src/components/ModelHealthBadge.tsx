import { useEffect, useState } from 'react'
import { getHealth } from '../api/health'
import type { Health } from '../api/health'
import { modelName } from '../format'

const REFRESH_MS = 30_000

/** "AI: 3 of 5 models up" in the header, with each model's state on hover. */
export function ModelHealthBadge() {
  const [health, setHealth] = useState<Health | null>(null)

  useEffect(() => {
    let cancelled = false
    const load = () =>
      getHealth()
        .then((next) => !cancelled && setHealth(next))
        .catch(() => !cancelled && setHealth(null))
    void load()
    const timer = setInterval(load, REFRESH_MS)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [])

  if (!health || health.models.length === 0) return null

  // A model nobody has called yet is presumed up until it fails.
  const up = health.models.filter((model) => model.state !== 'cooling_down').length
  const detail = health.models
    .map((model) => `${modelName(model.name)}: ${model.state.replace('_', ' ')}`)
    .join('\n')
  const level = up === 0 ? 'down' : up < health.panel_size ? 'degraded' : 'ok'

  return (
    <span className={`model-health model-health-${level}`} title={detail}>
      <span className="model-health-dot" aria-hidden="true" />
      AI: {up} of {health.models.length} models up
    </span>
  )
}
