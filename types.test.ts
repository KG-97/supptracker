import { describe, expect, it } from 'vitest'
import type { InteractionResponse, StackResponse } from './types'

const sampleResponse: InteractionResponse = {
  interaction: {
    id: 'caf-asp',
    a: 'caffeine',
    b: 'aspirin',
    bidirectional: true,
    mechanism: ['cytochrome'],
    severity: 'Moderate',
    evidence: 'B',
    effect: 'Example effect',
    action: 'Monitor',
    sources: ['source_caf_asp'],
    risk_score: 1.24,
  },
  risk_score: 1.24,
  sources: [
    {
      id: 'source_caf_asp',
      citation: 'Example citation',
      url: 'https://example.test',
    },
  ],
}

describe('API response typing', () => {
  it('accepts an interaction payload that matches the backend schema', () => {
    expect(sampleResponse.interaction.a).toBe('caffeine')
    expect(sampleResponse.interaction.risk_score).toBeCloseTo(sampleResponse.risk_score)
    expect(sampleResponse.sources[0]?.id).toBe('source_caf_asp')
  })

  it('supports additional stack metadata when present', () => {
    const stack: StackResponse = {
      items: ['creatine', 'caffeine'],
      resolved_items: ['creatine', 'caffeine'],
      matrix: [
        [null, 1.24],
        [1.24, null],
      ],
      interactions: [
        {
          a: 'creatine',
          b: 'caffeine',
          severity: 'Moderate',
          evidence: 'B',
          risk_score: 1.24,
          bucket: 'Caution',
          action: 'Monitor',
          action_resolved: 'Monitor closely',
        },
      ],
    }

    expect(stack.interactions[0]?.bucket).toBe('Caution')
    expect(stack.matrix?.[0]?.[1]).toBeCloseTo(1.24)
  })
})
