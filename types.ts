export type EvidenceGrade = 'A' | 'B' | 'C' | 'D'
export type SeverityLevel = 'None' | 'Mild' | 'Moderate' | 'Severe'

export interface Compound {
  id: string
  name: string
  synonyms?: string[] | null
  class?: string | null
  typicalDoseAmount?: string | null
  typicalDoseUnit?: string | null
  route?: string | null
  dose?: string | null
  externalIds?: Record<string, string>
  referenceUrls?: Record<string, string>
  externalLinks?: ExternalLink[]
  [key: string]: unknown
}

export interface ExternalLink {
  label?: string | null
  url?: string | null
  identifier?: string | null
  [key: string]: unknown
}

export interface Source {
  id?: string
  citation?: string
  title?: string
  reference?: string
  url?: string
  [key: string]: unknown
}

export interface InteractionRecord {
  id: string
  a: string
  b: string
  bidirectional?: boolean
  mechanism: string[]
  severity: SeverityLevel
  evidence: EvidenceGrade
  effect?: string
  action?: string
  sources: string[]
  [key: string]: unknown
}

export interface InteractionWithRisk extends InteractionRecord {
  risk_score: number
}

export interface InteractionResponse {
  interaction: InteractionRecord & Partial<InteractionWithRisk>
  risk_score: number
  sources: Source[]
}

export interface StackInteraction {
  a: string
  b: string
  severity: SeverityLevel | string
  evidence: EvidenceGrade | string
  risk_score: number
  effect?: string
  action?: string
  action_resolved?: string
  bucket?: string
}

export interface StackResponse {
  items?: string[]
  resolved_items?: string[]
  matrix?: (number | null)[][]
  cells?: StackInteraction[]
  interactions: StackInteraction[]
}

export interface HealthIssue {
  source: string
  error: string
}

export interface HealthResponse {
  status: 'healthy' | 'degraded'
  compounds_loaded: number
  interactions_loaded: number
  sources_loaded: number
  issues?: HealthIssue[]
}

export interface DocumentSearchResult {
  id: string
  title: string
  snippet: string
  score: number
  source?: string
}

export interface DocumentSearchMeta {
  uses_embeddings: boolean
  documents_indexed: number
  source?: string
  embedding_model?: string | null
}

export interface DocumentSearchResponse {
  results: DocumentSearchResult[]
  meta?: DocumentSearchMeta
}
