import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import type { Compound } from './types'

const apiMocks = vi.hoisted(() => {
  return {
    fetchHealth: vi.fn(async () => ({
      status: 'healthy',
      compounds_loaded: 1,
      interactions_loaded: 0,
      sources_loaded: 0,
    })),
    fetchAllCompounds: vi.fn(async () => [
      {
        id: 'caffeine',
        name: 'Caffeine',
        synonyms: ['coffee'],
        class: 'Stimulant',
        typicalDoseAmount: '100',
        typicalDoseUnit: 'mg',
        route: 'oral',
        externalIds: { pubchem: '2519', wikidata: 'Q30243' },
        referenceUrls: {
          pubchem: 'https://pubchem.ncbi.nlm.nih.gov/compound/2519',
          wikidata: 'https://www.wikidata.org/wiki/Q30243',
        },
      },
    ]),
    fetchInteractionsList: vi.fn(async () => [
      {
        id: 'caf-self',
        a: 'caffeine',
        b: 'caffeine',
        bidirectional: true,
        mechanism: [],
        severity: 'Mild',
        evidence: 'B',
        effect: 'Sample interaction',
        action: 'Monitor',
        sources: [],
        risk_score: 0.5,
      },
    ]),
    searchCompounds: vi.fn(async () => []),
    fetchInteraction: vi.fn(async () => ({
      interaction: {
        id: 'placeholder',
        a: 'a',
        b: 'b',
        bidirectional: true,
        mechanism: [],
        severity: 'None',
        evidence: 'A',
        effect: '',
        action: 'No issue',
        sources: [],
      },
      risk_score: 0,
      sources: [],
    })),
    checkStack: vi.fn(async () => ({ interactions: [] })),
  }
})

vi.mock('./api', () => ({
  fetchHealth: apiMocks.fetchHealth,
  fetchAllCompounds: apiMocks.fetchAllCompounds,
  fetchInteractionsList: apiMocks.fetchInteractionsList,
  searchCompounds: apiMocks.searchCompounds,
  fetchInteraction: apiMocks.fetchInteraction,
  checkStack: apiMocks.checkStack,
}))

describe('App external links', () => {
  beforeEach(() => {
    Object.values(apiMocks).forEach((mockFn) => mockFn.mockClear())
  })

  it('renders external reference links for compounds', async () => {
    render(<App />)

    const pubchemLink = await screen.findByRole('link', { name: 'Pubchem (2519)' })
    expect(pubchemLink).toHaveAttribute('href', 'https://pubchem.ncbi.nlm.nih.gov/compound/2519')
    expect(pubchemLink).toHaveAttribute('target', '_blank')

    const wikidataLink = await screen.findByRole('link', { name: 'Wikidata (Q30243)' })
    expect(wikidataLink).toHaveAttribute('href', 'https://www.wikidata.org/wiki/Q30243')
  })

  it('renders dataset external links provided as JSON strings', async () => {
    apiMocks.fetchAllCompounds.mockResolvedValueOnce([
      {
        id: 'creatine',
        name: 'Creatine',
        synonyms: [],
        dose: '3–5 g/day',
        external_links: JSON.stringify([
          { label: 'Examine', url: 'https://examine.com/supplements/creatine' },
        ]),
      } as unknown as Compound,
    ])

    render(<App />)

    const examineLink = await screen.findByRole('link', { name: 'Examine' })
    expect(examineLink).toHaveAttribute('href', 'https://examine.com/supplements/creatine')
  })

  it('shows the combined dose string when amount and unit are not provided separately', async () => {
    apiMocks.fetchAllCompounds.mockResolvedValueOnce([
      {
        id: 'creatine',
        name: 'Creatine',
        synonyms: [],
        dose: '3–5 g/day',
        external_links: JSON.stringify([
          { label: 'Examine', url: 'https://examine.com/supplements/creatine' },
        ]),
      } as unknown as Compound,
    ])

    render(<App />)

    expect(await screen.findByText('3–5 g/day')).toBeInTheDocument()
  })

  it('shows a health warning when the dataset is degraded', async () => {
    apiMocks.fetchHealth.mockResolvedValueOnce({
      status: 'degraded',
      compounds_loaded: 0,
      interactions_loaded: 0,
      sources_loaded: 0,
      issues: [{ source: 'compounds.csv', error: 'Missing data file' }],
    })

    render(<App />)

    const warningHeading = await screen.findByText('Dataset loaded with warnings')
    expect(warningHeading).toBeInTheDocument()
    expect(screen.getByText(/compounds\.csv/i)).toBeInTheDocument()
  })
})
