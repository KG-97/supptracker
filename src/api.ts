import type {
  Compound,
  DocumentSearchResponse,
  HealthResponse,
  InteractionResponse,
  InteractionWithRisk,
  StackResponse,
} from '../types'

const API_BASE = (() => {
  const rawEnvBase = import.meta.env.VITE_API_BASE
  if (typeof rawEnvBase === 'string' && rawEnvBase.trim()) {
    const trimmed = rawEnvBase.trim().replace(/\/$/, '')
    if (/^https?:\/\//i.test(trimmed)) {
      return trimmed
    }
    if (trimmed.startsWith('/')) {
      if (typeof window !== 'undefined' && window.location) {
        const isJsdom = typeof navigator !== 'undefined' && /jsdom/i.test(navigator.userAgent || '')
        if (!isJsdom) {
          return `${window.location.origin}${trimmed}`
        }
      }
      return `http://localhost:8000${trimmed}`
    }
    return trimmed
  }

  if (typeof window !== 'undefined') {
    const origin = window.location.origin
    const isJsdom = typeof navigator !== 'undefined' && /jsdom/i.test(navigator.userAgent || '')
    if (isJsdom || /localhost:(5173|4173)/.test(origin)) {
      return 'http://localhost:8000/api'
    }
    return `${origin.replace(/\/$/, '')}/api`
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

export async function searchDocuments(query: string, limit = 5): Promise<DocumentSearchResponse> {
  const trimmed = query.trim()
  if (!trimmed) {
    return { results: [], meta: { uses_embeddings: false, documents_indexed: 0 } }
  }
  const params = new URLSearchParams({ q: trimmed, limit: String(limit) })
  const data = await request<DocumentSearchResponse>(`/docs/search?${params.toString()}`)
  return {
    results: data.results ?? [],
    meta: data.meta,
  }
}

export async function fetchHealth(): Promise<HealthResponse> {
  return request<HealthResponse>('/health')
}

export async function fetchAllCompounds(): Promise<Compound[]> {
  const data = await request<{ compounds?: Compound[] }>('/compounds')
  return data.compounds ?? []
}

export async function fetchInteractionsList(): Promise<InteractionWithRisk[]> {
  const data = await request<{ interactions?: InteractionWithRisk[] }>('/interactions')
  return data.interactions ?? []
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

export type LabelStatementsStatus = 'available' | 'unavailable'

export interface LabelStatement {
  statement_id: string
  record_kind: string
  review_status: string
  supplement_id: string
  supplement_name: string
  supplement_kind: string
  drug_id: string
  drug_names_raw: string
  sentence: string
  matched_text: string
  section: string
  set_id: string
  label_id: string
  effective_time: string
  label_count: string
  source_url: string
  retrieved_at: string
  rights_status: string
  is_group_term: boolean
  label_url: string
}

export interface LabelStatementsSupplement {
  supplement_id: string
  supplement_name: string
  supplement_kind: string
  is_group_term: boolean
  pair_count: number
}

export interface LabelStatementsSummary {
  status: LabelStatementsStatus
  record_kind: string
  review_status: string
  disclaimer: string
  counts: {
    statements: number
    pairs: number
    supplements: number
    drugs: number
  }
  retrieved_at: {
    earliest: string | null
    latest: string | null
  }
  source: string
  license: string
  license_url: string
  supplements: LabelStatementsSupplement[]
  assessment?: 'not_assessed'
}

export interface LabelStatementsListResponse {
  status: LabelStatementsStatus
  record_kind: string
  review_status: string
  disclaimer: string
  total: number
  items: LabelStatement[]
  assessment?: 'not_assessed'
}

export interface LabelStatementsFilters {
  supplement?: string
  drug?: string
  q?: string
  limit?: number
  offset?: number
}

export async function fetchLabelStatementsSummary(): Promise<LabelStatementsSummary> {
  return request<LabelStatementsSummary>('/label-statements/summary')
}

export async function fetchLabelStatements(
  filters: LabelStatementsFilters = {}
): Promise<LabelStatementsListResponse> {
  const params = new URLSearchParams()

  if (filters.supplement) {
    params.set('supplement', filters.supplement)
  }
  if (filters.drug) {
    params.set('drug', filters.drug)
  }
  if (filters.q) {
    params.set('q', filters.q)
  }

  params.set('limit', String(filters.limit ?? 25))
  params.set('offset', String(filters.offset ?? 0))

  return request<LabelStatementsListResponse>(`/label-statements?${params.toString()}`)
}
