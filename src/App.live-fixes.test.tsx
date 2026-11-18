import '@testing-library/jest-dom/vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App, { didYouMean } from './App'

describe('didYouMean (Antigravity review, 19 Nov 2026)', () => {
  it('keeps the one-name wording, drops repeats and names the typo when there are several', () => {
    expect(didYouMean({})).toBe('')
    expect(didYouMean({ magnesum: [] })).toBe('')
    expect(didYouMean({ magnesum: ['Magnesium', 'Magnesium'] })).toBe(' Did you mean: Magnesium?')
    expect(didYouMean({ caferine: ['Caffeine'], caffiene: ['Caffeine'] })).toBe(
      ' Did you mean: Caffeine (for "caferine"), Caffeine (for "caffiene")?',
    )
  })
})

const mocks = vi.hoisted(() => ({
  fetchHealth: vi.fn(),
  fetchAllCompounds: vi.fn(),
  fetchInteractionsList: vi.fn(),
  fetchInteraction: vi.fn(),
  checkStack: vi.fn(),
  searchNames: vi.fn(),
  searchDocuments: vi.fn(),
  fetchLabelStatementLookup: vi.fn(),
  fetchLabelStatementsSummary: vi.fn(),
  fetchLabelStatements: vi.fn(),
}))

vi.mock('./api', () => ({
  ...mocks,
  ApiError: class ApiError extends Error {
    suggestions: Record<string, string[]>
    constructor(message: string, suggestions: Record<string, string[]>) {
      super(message)
      this.suggestions = suggestions
    }
  },
}))

import { ApiError } from './api'

describe('live search and check fixes', () => {
  afterEach(cleanup)

  beforeEach(() => {
    vi.resetAllMocks()
    mocks.fetchHealth.mockResolvedValue({ status: 'healthy', compounds_loaded: 0, interactions_loaded: 0, sources_loaded: 0 })
    mocks.fetchAllCompounds.mockResolvedValue([])
    mocks.fetchInteractionsList.mockResolvedValue([])
    mocks.fetchLabelStatementLookup.mockResolvedValue({ status: 'unavailable', names: [], pairs: [] })
    mocks.fetchLabelStatementsSummary.mockResolvedValue({ status: 'unavailable' })
    mocks.fetchLabelStatements.mockResolvedValue({ status: 'unavailable', items: [], total: 0 })
  })

  it('shows an unrecognised pair as informational with its suggestion', async () => {
    mocks.fetchInteraction.mockRejectedValue(new ApiError('Not recognised: magnesum', { magnesum: ['Magnesium'] }))
    render(<App />)
    fireEvent.change(screen.getByLabelText('Compound A'), { target: { value: 'magnesum' } })
    fireEvent.change(screen.getByLabelText('Compound B'), { target: { value: 'caffeine' } })
    fireEvent.click(screen.getByRole('button', { name: 'Check pair' }))
    const note = await screen.findByText(/Not recognised: magnesum/)
    expect(note).toHaveClass('status-info')
    expect(note).not.toHaveClass('status-error')
    expect(note).toHaveTextContent('Did you mean: Magnesium?')
  })

  it('reports unknown and duplicate stack entries while showing remaining results', async () => {
    mocks.checkStack.mockResolvedValue({
      evaluated_items: ['caffeine', 'aspirin'],
      unrecognised: ['magnesum'],
      duplicates_removed: ['aspirin'],
      suggestions: { magnesum: ['Magnesium'] },
      coverage: { total_pairs: 1, assessed_pairs: 0, not_assessed_pairs: 1 },
      interactions: [],
    })
    render(<App />)
    fireEvent.change(screen.getByLabelText('Supplement stack list'), {
      target: { value: 'caffeine, aspirin, aspirin, magnesum' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Check stack' }))
    const note = await screen.findByText(/Not recognised, so not checked: magnesum/)
    expect(note).toHaveTextContent('Duplicates removed: aspirin')
    expect(note).toHaveTextContent('Did you mean: Magnesium?')
    expect(screen.getByText(/No assessed interactions were found in caffeine, aspirin/)).toBeInTheDocument()
  })

  it('shows a label name without a no-match note', async () => {
    mocks.searchNames.mockResolvedValue({
      results: [],
      label_names: [{ id: 'melatonin', name: 'Melatonin', kind: 'supplement', statements: 9 }],
    })
    // The note under the search box (LabelStatementNameHits) asks the label lookup itself.
    mocks.fetchLabelStatementLookup.mockResolvedValue({
      status: 'available',
      assessment: 'not_assessed',
      disclaimer: '',
      message: '',
      names: [{
        input: 'melatonin',
        supplements: [{ supplement_id: 'melatonin', supplement_name: 'Melatonin', is_group_term: false, statements: 9 }],
        drug_total: 0,
        drugs: [],
      }],
      total_pairs: 0,
      truncated: false,
      pairs: [],
    })
    render(<App />)
    fireEvent.change(screen.getByLabelText('Compound search query'), { target: { value: 'melatonin' } })
    fireEvent.click(screen.getByRole('button', { name: 'Search' }))
    expect(await screen.findByRole('button', { name: 'Show statements for Melatonin' })).toBeInTheDocument()
    expect(screen.queryByText('No compounds matched your search.')).not.toBeInTheDocument()
  })
})
