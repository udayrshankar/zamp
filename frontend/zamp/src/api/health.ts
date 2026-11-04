import { request } from './client'

export interface ModelStatus {
  name: string
  state: 'ok' | 'failing' | 'cooling_down' | 'unknown'
  last_seconds: number | null
  last_error: string | null
}

export interface ModelCheck {
  models: ModelStatus[]
  panel_size: number
}

export interface Health extends ModelCheck {
  status: string
}

export function getHealth(): Promise<Health> {
  return request('/health')
}

/** Sends a tiny request to every model. The server reuses a check from the last minute. */
export function checkModels(): Promise<ModelCheck> {
  return request('/health/models/check', { method: 'POST' })
}
