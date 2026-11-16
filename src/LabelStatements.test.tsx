import '@testing-library/jest-dom/vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import LabelStatements from './LabelStatements'

// Without vitest globals the testing library does not unmount between tests (Claude Code, 2026-11-15).
afterEach(cleanup)

const disclaimer =
  'FDA-approved label text, quoted verbatim, not reviewed or assessed by SuppTracker, not medical advice, absence of a statement does not mean a combination is safe.'

const summary = {
  status: 'available' as const,
  record_kind: 'fda_label_statement',
  review_status: 'fda_approved_label_text_not_reviewed_by_supptracker',
  disclaimer,
  counts: {
    statements: 12,
    pairs: 6,
    supplements: 3,
    drugs: 4,
  },
  retrieved_at: {
    earliest: '2026-11-01T00:00:00Z',
    latest: '2026-11-02T00:00:00Z',
  },
  source: 'https://api.fda.gov/drug/label.json',
  license: 'CC0 1.0',
  license_url: 'https://open.fda.gov/license/',
  supplements: [
    {
      supplement_id: 'calcium',
      supplement_name: 'Calcium',
      supplement_kind: 'mineral_class',
      is_group_term: true,
      pair_count: 2,
    },
  ],
}

const statement = {
  statement_id: 'statement-1',
  record_kind: 'fda_label_statement',
  review_status: 'fda_approved_label_text_not_reviewed_by_supptracker',
  supplement_id: 'calcium',
  supplement_name: 'Calcium',
  supplement_kind: 'mineral_class',
  drug_id: 'levothyroxine',
  drug_names_raw: 'levothyroxine sodium',
  sentence: 'Calcium carbonate may reduce the absorption of levothyroxine.',
  matched_text: 'Calcium carbonate',
  section: 'DRUG INTERACTIONS',
  set_id: 'label-set-id',
  label_id: 'label-id',
  effective_time: '20261115',
  label_count: '2',
  source_url: 'https://api.fda.gov/drug/label.json',
  retrieved_at: '2026-11-15T00:00:00Z',
  rights_status: 'cc0_unless_otherwise_noted',
  is_group_term: true,
  label_url: 'https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=label-set-id',
}

const apiMocks = vi.hoisted(() => ({
  fetchLabelStatementsSummary: vi.fn(),
  fetchLabelStatements: vi.fn(),
}))

vi.mock('./api', () => ({
  fetchLabelStatementsSummary: apiMocks.fetchLabelStatementsSummary,
  fetchLabelStatements: apiMocks.fetchLabelStatements,
}))

describe('LabelStatements', () => {
  beforeEach(() => {
    apiMocks.fetchLabelStatementsSummary.mockReset()
    apiMocks.fetchLabelStatementsSummary.mockResolvedValue(summary)
    apiMocks.fetchLabelStatements.mockReset()
    apiMocks.fetchLabelStatements.mockResolvedValue({
      status: 'available',
      record_kind: 'fda_label_statement',
      review_status: 'fda_approved_label_text_not_reviewed_by_supptracker',
      disclaimer,
      total: 1,
      items: [statement],
    })
  })

  it('renders the disclaimer and corpus counts from the summary', async () => {
    render(<LabelStatements />)

    expect(await screen.findByText(disclaimer)).toBeInTheDocument()
    expect(screen.getByText('Statements')).toBeInTheDocument()
    expect(screen.getByText('12')).toBeInTheDocument()
    expect(screen.getByText('Pairs named together')).toBeInTheDocument()
    expect(screen.getByText('6')).toBeInTheDocument()
    expect(screen.getByText('Supplements')).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.getByText('Drugs')).toBeInTheDocument()
    expect(screen.getByText('4')).toBeInTheDocument()
  })

  it('renders a verbatim statement, DailyMed link, and group-term badge', async () => {
    render(<LabelStatements />)

    const sentence = await screen.findByTestId('label-statement-sentence-statement-1')
    expect(sentence.textContent).toBe(statement.sentence)

    const dailyMedLink = screen.getByRole('link', { name: 'View label on DailyMed' })
    expect(dailyMedLink).toHaveAttribute('href', statement.label_url)
    expect(dailyMedLink).toHaveAttribute('target', '_blank')
    expect(dailyMedLink).toHaveAttribute('rel', 'noopener noreferrer')
    expect(screen.getByText('group term')).toBeInTheDocument()
  })

  it('shows the exact not-assessed message for an empty result without no-interaction text', async () => {
    apiMocks.fetchLabelStatements.mockResolvedValueOnce({
      status: 'available',
      record_kind: 'fda_label_statement',
      review_status: 'fda_approved_label_text_not_reviewed_by_supptracker',
      disclaimer,
      assessment: 'not_assessed',
      total: 0,
      items: [],
    })

    render(<LabelStatements />)

    expect(
      await screen.findByText(
        'Not assessed. No FDA label statement was found for this search. This does not mean the combination is safe.'
      )
    ).toBeInTheDocument()
    expect(document.body.textContent?.toLowerCase()).not.toContain('no interaction')
  })

  it.each([
    ['an unavailable response', async () => {
      apiMocks.fetchLabelStatementsSummary.mockResolvedValueOnce({
        ...summary,
        status: 'unavailable',
      })
    }],
    ['a rejected request', async () => {
      apiMocks.fetchLabelStatements.mockRejectedValueOnce(new Error('Network failure'))
    }],
  ])('shows the unavailable message and no items after %s', async (_name, arrange) => {
    await arrange()

    render(<LabelStatements />)

    expect(
      await screen.findByText('FDA label statements are unavailable. Nothing has been assessed.')
    ).toBeInTheDocument()
    expect(screen.queryByTestId('label-statement-sentence-statement-1')).not.toBeInTheDocument()
  })
})
