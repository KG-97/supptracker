// ── Type definitions for SuppTracker ──────────────────────────────────────────

export interface CompoundHit { id: string; name: string; synonyms: string[] }

export interface CompoundDetail extends CompoundHit {
  compound_class: string; route: string; common_dose: string; qt_risk: string; notes: string
}

export interface InteractionSource { id: string; title?: string; citation?: string; identifier?: string; date?: string }

export interface InteractionDetail {
  compound_a: string; compound_b: string; severity?: string; evidence_grade?: string;
  mechanism_tags?: string; effect_summary?: string; score: number; bucket: string;
  action_resolved: string; sources: InteractionSource[]
}

export interface InteractionResponse { pair: { a: string; b: string }; interaction: InteractionDetail | null; found: boolean }

export interface StackCell { a: string; b: string; score: number; bucket: string; action: string; effect_summary?: string }

export interface StackResponse { items: string[]; matrix: (number | null)[][]; cells: StackCell[] }
