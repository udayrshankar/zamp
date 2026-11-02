import { useSyncExternalStore } from 'react'

function subscribe(onChange: () => void) {
  window.addEventListener('hashchange', onChange)
  return () => window.removeEventListener('hashchange', onChange)
}

function currentPath() {
  return window.location.hash.slice(1) || '/'
}

/** Hash routes give every invoice a real link and a working Back button. */
export function useHashRoute(): string {
  return useSyncExternalStore(subscribe, currentPath)
}

export function navigate(path: string) {
  window.location.hash = path
}
