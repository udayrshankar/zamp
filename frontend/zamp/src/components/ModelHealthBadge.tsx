import { useEffect, useState } from 'react'
import { checkModels, getHealth } from '../api/health'
import type { ModelCheck, ModelStatus } from '../api/health'
import { modelName } from '../format'

const REFRESH_MS = 30_000

const STATE_LABELS: Record<ModelStatus['state'], string> = {
  ok: 'online',
  failing: 'offline',
  cooling_down: 'offline, skipped for now',
  unknown: 'not checked yet',
}

function describe(model: ModelStatus): string {
  const time = model.last_seconds !== null ? ` (${model.last_seconds.toFixed(1)} s)` : ''
  const why = model.state !== 'ok' && model.last_error ? `: ${model.last_error}` : ''
  return `${modelName(model.name)}: ${STATE_LABELS[model.state]}${time}${why}`
}

/**
 * Checks every AI model when the page loads, then keeps the count fresh from
 * what real invoices find. Only models that actually answered count as up.
 */
export function ModelHealthBadge() {
  const [health, setHealth] = useState<ModelCheck | null>(null)
  const [checking, setChecking] = useState(true)

  useEffect(() => {
    let cancelled = false
    checkModels()
      .then((result) => !cancelled && setHealth(result))
      .catch(() => undefined)
      .finally(() => !cancelled && setChecking(false))
    const timer = setInterval(() => {
      getHealth()
        .then((result) => !cancelled && setHealth(result))
        .catch(() => undefined)
    }, REFRESH_MS)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [])

  if (checking && !health) {
    return (
      <span className="model-health model-health-checking">
        <span className="model-health-dot" aria-hidden="true" />
        Checking AI models…
      </span>
    )
  }
  if (!health || health.models.length === 0) return null

  const up = health.models.filter((model) => model.state === 'ok').length
  const level = up === 0 ? 'down' : up < health.panel_size ? 'degraded' : 'ok'

  return (
    <span
      className={`model-health model-health-${level}`}
      title={health.models.map(describe).join('\n')}
    >
      <span className="model-health-dot" aria-hidden="true" />
      AI: {up} of {health.models.length} models online
    </span>
  )
}
