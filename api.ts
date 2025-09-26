import type { Compound, InteractionResponse, StackResponse } from './types'

const API_BASE = (() => {
  const envBase = import.meta.env.VITE_API_BASE?.trim()
  if (envBase) return envBase.replace(/\/$/, '')

  if (typeof window !== 'undefined') {
    const origin = window.location.origin
    if (/localhost:(5173|4173)/.test(origin)) {
      return 'http://localhost:8000/api'
    }
    return '/api'
  }

  return 'http://localhost:8000/api'
})()

async function parseError(res: Response, fallback: string) {
  try {
    const text = (await res.text()).trim();
    if (!text) return fallback;

    try {
      const data = JSON.parse(text);
      if (typeof data === 'string') return data;
      if (data && typeof data.message === 'string') return data.message;
      if (data && typeof data.detail === 'string') return data.detail;
      if (data && typeof data.error === 'string') return data.error;
      return text;
    } catch {
      return text
    }
  } catch {
    return fallback
  }
}

function resolveUrl(path: string): string {
  const normalized = path.startsWith('/') ? path : `/${path}`
  return `${API_BASE}${normalized}`
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(resolveUrl(path), init)
  if (!res.ok) {
    throw new Error(await parseError(res, 'Request failed'))
  }
  return res.json() as Promise<T>
}

export async function searchCompounds(query: string): Promise<Compound[]> {
  if (!query.trim()) return []
  const data = await request<{ results?: Compound[]; compounds?: Compound[] }>(
    `/search?q=${encodeURIComponent(query)}`
  )
  return data.results ?? data.compounds ?? []
}

export async function fetchInteraction(a: string, b: string): Promise<InteractionResponse> {
  return request<InteractionResponse>(
    `/interaction?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`
  )
}

export async function checkStack(compounds: string[]): Promise<StackResponse> {
  return request<StackResponse>('/stack/check', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ compounds }),
  })
}
