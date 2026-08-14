// ── Helper functions for SuppTracker ──────────────────────────────────────────

export function severityBadgeClass(s?: string): string {
  const k = (s || '').toLowerCase()
  if (k === 'none' || k === 'low') return 'badge badge-none'
  if (k === 'mild') return 'badge badge-mild'
  if (k === 'moderate' || k === 'medium') return 'badge badge-moderate'
  if (k === 'high' || k === 'severe') return 'badge badge-high'
  if (k === 'critical') return 'badge badge-critical'
  return 'badge badge-none'
}

export function bucketCellClass(b?: string | null): string {
  if (!b) return 'cell-empty'
  const k = b.toLowerCase()
  if (k === 'low' || k === 'none') return 'cell-low'
  if (k === 'mild') return 'cell-mild'
  if (k === 'medium' || k === 'moderate') return 'cell-medium'
  if (k === 'high' || k === 'severe') return 'cell-high'
  if (k === 'critical') return 'cell-critical'
  return 'cell-empty'
}

export function scoreToColor(score: number): string {
  if (score <= 0.3) return '#22c55e'
  if (score <= 0.9) return '#eab308'
  if (score <= 1.8) return '#f97316'
  if (score <= 2.7) return '#ef4444'
  return '#9333ea'
}

export function scoreBarPct(score: number): number {
  return Math.min(100, (score / 3.5) * 100)
}

export function classEmoji(cls: string): string {
  const map: Record<string, string> = {
    amino_acid: '🧬', amino_acid_derivative: '🧬', stimulant: '⚡', mineral: '💎',
    fatty_acid: '🐟', fat_soluble_vitamin: '☀️', water_soluble_vitamin: '🍊',
    adaptogen: '🌿', hormone: '🌙', antioxidant: '🛡️', alkaloid: '🍃',
    mushroom: '🍄', neurotransmitter: '🧠', macronutrient: '💪', microbiome: '🦠', protein: '💪',
    // Expanded compound classes
    'amino acid': '🧬', 'amino acid derivative': '🧬', 'herb adaptogen': '🌿',
    'herb nootropic': '🧠', 'herb': '🌿', polyphenol: '🍇', vitamin: '💊',
    'choline donor': '🧠', 'amino sugar': '🦴', glycosaminoglycan: '🦴',
    organosulfur: '⚗️', quinone: '⚡', ergogenic: '💪', 'fatty acid': '🐟',
  }
  return map[cls] || '💊'
}
