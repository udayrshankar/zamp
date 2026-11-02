import { request } from './client'

export interface ModelStatus {
  name: string
  state: 'ok' | 'cooling_down' | 'unknown'
  last_seconds: number | null
  last_error: string | null
}

export interface Health {
  status: string
  models: ModelStatus[]
  panel_size: number
}

export function getHealth(): Promise<Health> {
  return request('/health')
}
