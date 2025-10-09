import { afterEach, describe, expect, it, vi } from 'vitest'
import { searchCompounds } from '../api'
import type { Compound } from '../types'

const originalFetch = global.fetch

afterEach(() => {
  vi.restoreAllMocks()
  global.fetch = originalFetch
})

describe('searchCompounds', () => {
  it('requests the search endpoint with the encoded query parameter', async () => {
    const mockResults: Compound[] = [
      { id: 'caffeine', name: 'Caffeine', synonyms: ['coffee'] },
    ]

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ results: mockResults }),
    } as Partial<Response>)

    global.fetch = fetchMock as unknown as typeof fetch

    const results = await searchCompounds('caffeine')

    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8000/api/search?q=caffeine',
      undefined
    )
    expect(results).toEqual(mockResults)
  })

  it('encodes special characters before requesting the backend', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ results: [] }),
    } as Partial<Response>)

    global.fetch = fetchMock as unknown as typeof fetch

    await searchCompounds('vitamin c + zinc')

    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8000/api/search?q=vitamin%20c%20%2B%20zinc',
      undefined
    )
  })
})
