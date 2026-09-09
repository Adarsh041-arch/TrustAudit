export function apiFetch(input: string, init: RequestInit = {}) {
  const headers = new Headers(init.headers)
  const token = sessionStorage.getItem('audit_access_token')
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const url = new URL(input, window.location.href)
  // The server derives tenant membership from authenticated identity.
  if (token) url.searchParams.delete('tenant_id')
  return fetch(url, { ...init, headers })
}
