import '@testing-library/jest-dom/vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import LabelStatements from './LabelStatements'
import LabelStatementMatches, { LabelStatementNameHits } from './LabelStatementMatches'

const apiMocks = vi.hoisted(() => ({
  fetchLabelStatementLookup: vi.fn(),
  fetchLabelStatementsSummary: vi.fn(),
  fetchLabelStatements: vi.fn(),
}))

vi.mock('./api', () => ({
  fetchLabelStatementLookup: apiMocks.fetchLabelStatementLookup,
  fetchLabelStatementsSummary: apiMocks.fetchLabelStatementsSummary,
  fetchLabelStatements: apiMocks.fetchLabelStatements,
}))

const envelope = {
  status: 'available',
  record_kind: 'fda_label_statement',
  review_status: 'fda_approved_label_text_not_reviewed_by_supptracker',
  disclaimer: 'FDA-approved label text, quoted verbatim.',
  assessment: 'not_assessed',
}

describe('label statement lookups', () => {
  afterEach(cleanup)

  beforeEach(() => {
    apiMocks.fetchLabelStatementLookup.mockReset()
    apiMocks.fetchLabelStatementsSummary.mockReset()
    apiMocks.fetchLabelStatements.mockReset()
  })

  it('does nothing until a check is requested', () => {
    render(<LabelStatementMatches names={['a', 'b']} requestId={0} />)

    expect(apiMocks.fetchLabelStatementLookup).not.toHaveBeenCalled()
    expect(screen.queryByRole('region')).not.toBeInTheDocument()
  })

  it('never implies an assessment when the lookup fails', async () => {
    apiMocks.fetchLabelStatementLookup.mockRejectedValueOnce(new Error('offline'))

    render(<LabelStatementMatches names={['caffeine', 'adenosine']} requestId={1} />)

    expect(
      await screen.findByText('FDA label statements could not be checked. Nothing has been assessed.')
    ).toBeInTheDocument()
  })

  it('offers the statements for a searched name and reports the choice', async () => {
    apiMocks.fetchLabelStatementLookup.mockResolvedValueOnce({
      ...envelope,
      message: '',
      names: [
        {
          input: 'melatonin',
          supplements: [
            { supplement_id: 'melatonin', supplement_name: 'Melatonin', is_group_term: false, statements: 9 },
          ],
          drug_total: 0,
          drugs: [],
        },
      ],
      total_pairs: 0,
      truncated: false,
      pairs: [],
    })
    const onShow = vi.fn()

    render(<LabelStatementNameHits name="melatonin" requestId={1} onShow={onShow} />)

    fireEvent.click(await screen.findByRole('button', { name: 'Show statements for Melatonin' }))
    expect(apiMocks.fetchLabelStatementLookup).toHaveBeenCalledWith(['melatonin'])
    expect(onShow).toHaveBeenCalledWith({ supplement: 'melatonin' })
    expect(screen.getByText(/not assessed by SuppTracker/)).toBeInTheDocument()
  })

  it('says so when a searched name is not in the collection', async () => {
    apiMocks.fetchLabelStatementLookup.mockResolvedValueOnce({
      ...envelope,
      message: '',
      names: [{ input: 'creatine', supplements: [], drug_total: 0, drugs: [] }],
      total_pairs: 0,
      truncated: false,
      pairs: [],
    })

    render(<LabelStatementNameHits name="creatine" requestId={1} onShow={vi.fn()} />)

    expect(
      await screen.findByText(/is not named in the FDA label statement collection either/)
    ).toBeInTheDocument()
  })

  it('applies a filter requested from elsewhere on the page', async () => {
    apiMocks.fetchLabelStatementsSummary.mockResolvedValue({
      ...envelope,
      counts: { statements: 1, pairs: 1, supplements: 1, drugs: 1 },
      retrieved_at: { earliest: null, latest: null },
      source: '',
      license: 'CC0',
      license_url: '',
      supplements: [
        { supplement_id: 'melatonin', supplement_name: 'Melatonin', supplement_kind: 'other', is_group_term: false, pair_count: 1 },
      ],
    })
    apiMocks.fetchLabelStatements.mockResolvedValue({ ...envelope, total: 0, items: [] })

    render(<LabelStatements request={{ supplement: 'melatonin', token: 1 }} />)

    await waitFor(() =>
      expect(apiMocks.fetchLabelStatements).toHaveBeenCalledWith(
        expect.objectContaining({ supplement: 'melatonin', drug: undefined, q: undefined, offset: 0 })
      )
    )
  })
})
