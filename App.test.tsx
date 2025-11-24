import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import type { Compound } from './types'

const defaultHealthResponse = {
  status: 'healthy',
  compounds_loaded: 1,
  interactions_loaded: 0,
  sources_loaded: 0,
}

const defaultCompoundList = [
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
]

const defaultInteractionsList = [
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
]

const apiMocks = vi.hoisted(() => {
  return {
    fetchHealth: vi.fn(async () => defaultHealthResponse),
    fetchAllCompounds: vi.fn(async () => defaultCompoundList),
    fetchInteractionsList: vi.fn(async () => defaultInteractionsList),
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
    apiMocks.fetchHealth.mockReset()
    apiMocks.fetchHealth.mockResolvedValue(defaultHealthResponse)

    apiMocks.fetchAllCompounds.mockReset()
    apiMocks.fetchAllCompounds.mockResolvedValue(defaultCompoundList)

    apiMocks.fetchInteractionsList.mockReset()
    apiMocks.fetchInteractionsList.mockResolvedValue(defaultInteractionsList)

    apiMocks.searchCompounds.mockReset()
    apiMocks.searchCompounds.mockResolvedValue([])

    apiMocks.fetchInteraction.mockReset()
    apiMocks.fetchInteraction.mockResolvedValue({
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
    })

    apiMocks.checkStack.mockReset()
    apiMocks.checkStack.mockResolvedValue({ interactions: [] })
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

  it('renders dataset external links provided as object maps', async () => {
    apiMocks.fetchAllCompounds.mockImplementation(async () => [
      {
        id: 'ashwagandha',
        name: 'Ashwagandha',
        synonyms: [],
        route: 'oral',
        external_links: {
          examine: 'https://examine.com/supplements/ashwagandha',
        },
      } as unknown as Compound,
    ])

    render(<App />)

    const compoundHeading = await screen.findByText('Ashwagandha')
    const compoundItem = compoundHeading.closest('li')
    expect(compoundItem).not.toBeNull()
    const examineLink = within(compoundItem as HTMLElement).getByRole('link', { name: 'Examine' })
    expect(examineLink).toHaveAttribute('href', 'https://examine.com/supplements/ashwagandha')
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

  it('normalises synonyms provided as a delimited string', async () => {
    apiMocks.fetchAllCompounds.mockImplementation(async () => [
      {
        id: 'rhodiola',
        name: 'Rhodiola rosea',
        synonyms: null,
        synonyms_string: 'arctic root; roseroot',
      } as unknown as Compound,
    ])

    render(<App />)

    const compoundHeading = await screen.findByText('Rhodiola rosea')
    const compoundItem = compoundHeading.closest('li')
    expect(compoundItem).not.toBeNull()
    const compoundScope = within(compoundItem as HTMLElement)
    expect(compoundScope.getByText('Also known as')).toBeInTheDocument()
    expect(compoundScope.getByText('arctic root, roseroot')).toBeInTheDocument()
  })

  it('requires at least two compounds before running a stack check', async () => {
    render(<App />)

    const textarea = await screen.findByLabelText(/supplement stack list/i)
    const form = textarea.closest('form') as HTMLFormElement
    const submitButton = within(form).getByRole('button', { name: /check stack/i })
    fireEvent.change(textarea, { target: { value: 'Creatine' } })
    fireEvent.click(submitButton)

    expect(await screen.findByText(/at least two compounds/i)).toBeInTheDocument()
    expect(apiMocks.checkStack).not.toHaveBeenCalled()
  })

  it('surfaces resolved stack items returned by the API', async () => {
    apiMocks.checkStack.mockResolvedValueOnce({
      interactions: [
        {
          a: 'caffeine',
          b: 'aspirin',
          severity: 'Moderate',
          evidence: 'B',
          risk_score: 1.6,
        },
      ],
      resolved_items: ['caffeine', 'aspirin'],
    })

    render(<App />)

    const textarea = await screen.findByLabelText(/supplement stack list/i)
    const form = textarea.closest('form') as HTMLFormElement
    const submitButton = within(form).getByRole('button', { name: /check stack/i })
    fireEvent.change(textarea, { target: { value: 'Coffee\nAspirin' } })
    fireEvent.click(submitButton)

    expect(apiMocks.checkStack).toHaveBeenCalledWith(['Coffee', 'Aspirin'])
    expect(await screen.findByText(/interactions found for caffeine, aspirin/i)).toBeInTheDocument()
  })
})
