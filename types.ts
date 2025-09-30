export interface Compound {
  id: string
  name: string
  synonyms: string[]
  class?: string | null
  typicalDoseAmount?: string | null
  typicalDoseUnit?: string | null
  route?: string | null
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
  compound_a: string
  compound_b: string
  bidirectional: boolean
  severity: 'None' | 'Mild' | 'Moderate' | 'Severe' | string
  evidence_grade: 'A' | 'B' | 'C' | 'D' | string
  effect?: string | null
  action?: string | null
  mechanism_tags?: string | null
  source_ids?: string | null
  score: number
  bucket: string
  action_resolved?: string | null
  sources: Source[]
  [key: string]: unknown
}

export interface InteractionPair {
  a: string
  b: string
}

export interface InteractionResponse {
  pair: InteractionPair
  interaction: InteractionRecord
}

export interface StackInteraction {
  a: string
  b: string
  severity: string
  evidence: string
  score: number
  risk_score: number
  bucket?: string
  effect?: string | null
  action?: string | null
  action_resolved?: string | null
}

export interface StackResponse {
  items?: string[]
  matrix?: (number | null)[][]
  cells?: StackInteraction[]
  interactions: StackInteraction[]
}
