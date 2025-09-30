import { describe, expect, it } from 'vitest'
import type { InteractionResponse, StackResponse } from './types'

const sampleResponse: InteractionResponse = {
  pair: { a: 'creatine', b: 'caffeine' },
  interaction: {
    id: 'creatine_caffeine',
    compound_a: 'creatine',
    compound_b: 'caffeine',
    bidirectional: true,
    severity: 'Moderate',
    evidence_grade: 'B',
    effect: 'Test effect',
    action: 'Monitor',
    mechanism_tags: 'CYP3A4_inhibition',
    source_ids: 'source_creatine_caffeine',
    score: 1.23,
    bucket: 'Caution',
    action_resolved: 'Monitor closely',
    sources: [
      {
        id: 'source_creatine_caffeine',
        citation: 'Sample citation',
        url: 'https://example.test',
      },
    ],
  },
}

describe('API response typing', () => {
  it('accepts an interaction payload that matches the backend schema', () => {
    expect(sampleResponse.interaction.compound_a).toBe(sampleResponse.pair.a)
    expect(sampleResponse.interaction.score).toBeGreaterThan(0)
    expect(sampleResponse.interaction.sources[0]?.citation).toBe('Sample citation')
  })

  it('supports additional stack metadata when present', () => {
    const stack: StackResponse = {
      items: ['creatine', 'caffeine'],
      matrix: [
        [null, 1.23],
        [1.23, null],
      ],
      interactions: [
        {
          a: 'creatine',
          b: 'caffeine',
          severity: 'Moderate',
          evidence: 'B',
          score: 1.23,
          risk_score: 1.23,
          bucket: 'Caution',
          action: 'Monitor',
          action_resolved: 'Monitor closely',
        },
      ],
    }

    expect(stack.interactions[0]?.bucket).toBe('Caution')
    expect(stack.matrix?.[0]?.[1]).toBeCloseTo(1.23)
  })
})
