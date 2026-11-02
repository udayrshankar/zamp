export async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init)
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    // Domain errors carry `message`; FastAPI validation errors carry `detail`.
    throw new Error(
      body?.message ?? body?.detail?.[0]?.msg ?? `Request failed (${response.status})`,
    )
  }
  return response.status === 204 ? (undefined as T) : response.json()
}
