export interface Compound {
  id: string
  name: string
  synonyms: string[]
  class?: string | null
  typicalDoseAmount?: string | null
  typicalDoseUnit?: string | null
  route?: string | null
  externalIds?: Record<string, string>
  referenceUrls?: Record<string, string>
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
  bidirectional: boolean
  mechanism: string[]
  severity: 'None' | 'Mild' | 'Moderate' | 'Severe'
  evidence: 'A' | 'B' | 'C' | 'D'
  effect: string
  action: string
  sources: string[]
}

export interface InteractionWithRisk extends InteractionRecord {
  risk_score: number
}

export interface InteractionResponse {
  interaction: InteractionRecord
  risk_score: number
  sources: Source[]
}

export interface StackInteraction {
  a: string
  b: string
  severity: string
  evidence: string
  risk_score: number
  effect?: string
  action?: string
}

export interface StackResponse {
  interactions: StackInteraction[]
}

export interface HealthResponse {
  status: string
  compounds_loaded: number
  interactions_loaded: number
  sources_loaded: number
}
