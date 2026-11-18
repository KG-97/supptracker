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

  const summaryReply = {
    ...envelope,
    counts: { statements: 30, pairs: 2, supplements: 1, drugs: 2 },
    retrieved_at: { earliest: null, latest: null },
    source: '',
    license: 'CC0',
    license_url: '',
    supplements: [
      { supplement_id: 'melatonin', supplement_name: 'Melatonin', supplement_kind: 'other', is_group_term: false, pair_count: 2 },
    ],
  }

  function statements(prefix: string, count: number) {
    return Array.from({ length: count }, (_, index) => ({
      statement_id: `${prefix}${index}`,
      sentence: `${prefix} sentence ${index}.`,
      supplement_name: 'Melatonin',
      is_group_term: false,
      drug_names_raw: 'DRUG',
      label_count: 1,
      effective_time: '20260101',
      label_url: 'https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=x',
    }))
  }

  it('does not let the unfiltered first page replace a filter requested during loading', async () => {
    apiMocks.fetchLabelStatementsSummary.mockResolvedValue(summaryReply)
    apiMocks.fetchLabelStatements.mockResolvedValue({ ...envelope, total: 1, items: statements('filtered', 1) })

    render(<LabelStatements request={{ supplement: 'melatonin', token: 1 }} />)

    expect(await screen.findByText('filtered sentence 0.')).toBeInTheDocument()
    await waitFor(() => expect(apiMocks.fetchLabelStatementsSummary).toHaveBeenCalled())
    // Every list request carried the requested supplement; none was the unfiltered first page.
    for (const call of apiMocks.fetchLabelStatements.mock.calls) {
      expect(call[0]).toEqual(expect.objectContaining({ supplement: 'melatonin' }))
    }
  })

  it('ignores an older list reply that arrives after a newer one', async () => {
    apiMocks.fetchLabelStatementsSummary.mockResolvedValue(summaryReply)
    let slowReply: (value: unknown) => void = () => {}
    apiMocks.fetchLabelStatements.mockReturnValueOnce(
      new Promise((resolve) => {
        slowReply = resolve
      })
    )
    apiMocks.fetchLabelStatements.mockResolvedValue({ ...envelope, total: 1, items: statements('newer', 1) })

    const { rerender } = render(<LabelStatements />)
    await waitFor(() => expect(apiMocks.fetchLabelStatements).toHaveBeenCalledTimes(1))

    rerender(<LabelStatements request={{ supplement: 'melatonin', token: 1 }} />)
    expect(await screen.findByText('newer sentence 0.')).toBeInTheDocument()

    slowReply({ ...envelope, total: 1, items: statements('older', 1) })
    await waitFor(() => expect(screen.getByText('newer sentence 0.')).toBeInTheDocument())
    expect(screen.queryByText('older sentence 0.')).not.toBeInTheDocument()
  })

  it('pages with the filters that produced the list, not with edited boxes', async () => {
    apiMocks.fetchLabelStatementsSummary.mockResolvedValue(summaryReply)
    apiMocks.fetchLabelStatements.mockResolvedValue({ ...envelope, total: 30, items: statements('page', 25) })

    render(<LabelStatements request={{ supplement: 'melatonin', token: 1 }} />)
    await screen.findByText('page sentence 0.')

    fireEvent.change(screen.getByLabelText('Drug'), { target: { value: 'warfarin' } })
    fireEvent.click(screen.getByRole('button', { name: 'Show more' }))

    await waitFor(() =>
      expect(apiMocks.fetchLabelStatements).toHaveBeenLastCalledWith(
        expect.objectContaining({ supplement: 'melatonin', drug: undefined, offset: 25 })
      )
    )
  })

  it('shows the names that were typed beside the label names, and marks combination products', async () => {
    const lookup = pairsLookup(1)
    lookup.pairs[0] = { ...lookup.pairs[0], supplement_input: 'K2', drug_input: 'warfarin', combination_product: true } as typeof lookup.pairs[0]
    apiMocks.fetchLabelStatementLookup.mockResolvedValueOnce(lookup)

    render(<LabelStatementMatches names={['K2', 'warfarin']} requestId={1} />)

    expect(
      await screen.findByText(/Matched from the names you entered: “K2” and “warfarin”/)
    ).toBeInTheDocument()
    expect(screen.getByText('combination product')).toBeInTheDocument()
  })

  it('repeats the input rule when the lookup rejects the names, and nothing else', async () => {
    apiMocks.fetchLabelStatementLookup.mockRejectedValueOnce(new Error('Give between 1 and 20 names.'))
    const { unmount } = render(<LabelStatementMatches names={['a', 'b']} requestId={1} />)
    expect(
      await screen.findByText(
        'FDA label statements could not be checked. Nothing has been assessed. Give between 1 and 20 names.'
      )
    ).toBeInTheDocument()
    unmount()

    apiMocks.fetchLabelStatementLookup.mockRejectedValueOnce(new Error('<html>502 Bad Gateway</html>'))
    render(<LabelStatementMatches names={['a', 'b']} requestId={1} />)
    expect(
      await screen.findByText('FDA label statements could not be checked. Nothing has been assessed.')
    ).toBeInTheDocument()
  })

  function pairsLookup(count: number) {
    return {
      ...envelope,
      message: 'FDA label statements name these together.',
      names: [],
      total_pairs: count,
      truncated: false,
      pairs: Array.from({ length: count }, (_, index) => ({
        supplement_input: 'calcium',
        drug_input: `drug ${index}`,
        supplement_id: 'calcium',
        supplement_name: 'Calcium supplements',
        is_group_term: false,
        drug_id: `drug-${index}`,
        drug_names_raw: `DRUG ${index}`,
        labels: 10 - index,
        total: 1,
        items: [
          {
            statement_id: `s${index}`,
            sentence: `Sentence ${index}.`,
            label_count: 1,
            label_url: 'https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=x',
          },
        ],
      })),
    }
  }

  it('folds pairs after the first three and can open or fold them all', async () => {
    apiMocks.fetchLabelStatementLookup.mockResolvedValueOnce(pairsLookup(5))

    const { container } = render(<LabelStatementMatches names={['calcium', 'x']} requestId={1} />)

    await screen.findByText('Sentence 0.')
    const opened = () => Array.from(container.querySelectorAll('details')).map((item) => item.open)
    expect(opened()).toEqual([true, true, true, false, false])
    // Folding removes nothing from the page: every sentence is still there to open.
    expect(screen.getByText('Sentence 4.')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Expand all 5 pairs' }))
    expect(opened()).toEqual([true, true, true, true, true])

    fireEvent.click(screen.getByRole('button', { name: 'Collapse all' }))
    expect(opened()).toEqual([false, false, false, false, false])
  })

  it('keeps a short result open and offers no expand control', async () => {
    apiMocks.fetchLabelStatementLookup.mockResolvedValueOnce(pairsLookup(2))

    const { container } = render(<LabelStatementMatches names={['calcium', 'x']} requestId={1} />)

    await screen.findByText('Sentence 0.')
    expect(Array.from(container.querySelectorAll('details')).map((item) => item.open)).toEqual([true, true])
    expect(screen.queryByRole('button', { name: /expand all/i })).not.toBeInTheDocument()
  })

  it('only says "either" when the compound search found nothing', async () => {
    const unnamed = {
      ...envelope,
      message: '',
      names: [{ input: 'aspirin', supplements: [], drug_total: 0, drugs: [] }],
      total_pairs: 0,
      truncated: false,
      pairs: [],
    }
    apiMocks.fetchLabelStatementLookup.mockResolvedValue(unnamed)

    const { unmount } = render(
      <LabelStatementNameHits name="aspirin" requestId={1} compoundMatches={3} onShow={vi.fn()} />
    )
    expect(
      await screen.findByText('“aspirin” is not named in the FDA label statement collection.')
    ).toBeInTheDocument()
    unmount()

    render(<LabelStatementNameHits name="aspirin" requestId={1} compoundMatches={0} onShow={vi.fn()} />)
    expect(
      await screen.findByText('“aspirin” is not named in the FDA label statement collection either.')
    ).toBeInTheDocument()
  })

  it('labels a drug hit with its name and still filters by its identifier', async () => {
    apiMocks.fetchLabelStatementLookup.mockResolvedValueOnce({
      ...envelope,
      message: '',
      names: [
        {
          input: 'sodium',
          supplements: [],
          drug_total: 1,
          drugs: [
            {
              drug_id: 'omeprazole+sodium-bicarbonate',
              drug_names_raw: 'OMEPRAZOLE; SODIUM BICARBONATE',
              statements: 6,
            },
          ],
        },
      ],
      total_pairs: 0,
      truncated: false,
      pairs: [],
    })
    const onShow = vi.fn()

    render(<LabelStatementNameHits name="sodium" requestId={1} onShow={onShow} />)

    fireEvent.click(
      await screen.findByRole('button', { name: 'Show statements for OMEPRAZOLE; SODIUM BICARBONATE' })
    )
    expect(onShow).toHaveBeenCalledWith({ drug: 'omeprazole+sodium-bicarbonate' })
  })
})
