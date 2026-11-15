import { afterEach, describe, expect, it, vi } from 'vitest'
import { checkStack, searchCompounds } from '../api'
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

describe('error messages', () => {
  function failWith(status: number, body: string) {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status,
      text: async () => body,
    } as Partial<Response>) as unknown as typeof fetch
  }

  async function messageFrom(run: () => Promise<unknown>): Promise<string> {
    try {
      await run()
    } catch (error) {
      return error instanceof Error ? error.message : String(error)
    }
    throw new Error('expected the request to fail')
  }

  it('turns a validation list into a sentence instead of raw JSON', async () => {
    // The exact body the API sends for a stack of 21 names.
    failWith(
      422,
      JSON.stringify({
        detail: [
          {
            type: 'value_error',
            loc: ['body', 'compounds'],
            msg: 'Value error, A stack may contain at most 20 compounds',
            input: ['antacids', 'calcium'],
            ctx: { error: {} },
          },
        ],
      })
    )

    expect(await messageFrom(() => checkStack(['a', 'b']))).toBe(
      'A stack may contain at most 20 compounds.'
    )
  })

  it('keeps a plain-text reason as sent', async () => {
    failWith(404, JSON.stringify({ detail: 'Compound not found: unobtainium' }))

    expect(await messageFrom(() => checkStack(['a', 'b']))).toBe('Compound not found: unobtainium')
  })

  it('never shows an unexplained JSON body or an HTML error page', async () => {
    failWith(500, JSON.stringify({ trace: ['a', 'b'], code: 17 }))
    expect(await messageFrom(() => checkStack(['a', 'b']))).toBe('Request failed (HTTP 500)')

    failWith(502, '<html><body><h1>502 Bad Gateway</h1></body></html>')
    expect(await messageFrom(() => checkStack(['a', 'b']))).toBe('Request failed (HTTP 502)')
  })
})
