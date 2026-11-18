import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, test, vi } from 'vitest'
import App, { parseStackData } from './App'
import type { Compound, StackResponse } from './types'

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
    fetchLabelStatementsSummary: vi.fn(async () => ({
      status: 'unavailable',
      disclaimer: 'FDA-approved label text, quoted verbatim, not reviewed or assessed by SuppTracker, not medical advice, absence of a statement does not mean a combination is safe.',
    })),
    fetchLabelStatements: vi.fn(async () => ({
      status: 'unavailable',
      disclaimer: 'FDA-approved label text, quoted verbatim, not reviewed or assessed by SuppTracker, not medical advice, absence of a statement does not mean a combination is safe.',
      total: 0,
      items: [],
    })),
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
    fetchLabelStatementLookup: vi.fn(async (): Promise<any> => ({
      status: 'unavailable',
      assessment: 'not_assessed',
      disclaimer: '',
      message: '',
      names: [],
      total_pairs: 0,
      truncated: false,
      pairs: [],
    })),
  }
})

// The label statement components import the module in src directly. Mock their calls there so
// these tests never reach a real server.
vi.mock('./src/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./src/api')>()),
  fetchLabelStatementsSummary: apiMocks.fetchLabelStatementsSummary,
  fetchLabelStatements: apiMocks.fetchLabelStatements,
  fetchLabelStatementLookup: apiMocks.fetchLabelStatementLookup,
}))

vi.mock('./api', () => ({
  fetchHealth: apiMocks.fetchHealth,
  fetchAllCompounds: apiMocks.fetchAllCompounds,
  fetchInteractionsList: apiMocks.fetchInteractionsList,
  fetchLabelStatementsSummary: apiMocks.fetchLabelStatementsSummary,
  fetchLabelStatements: apiMocks.fetchLabelStatements,
  searchCompounds: apiMocks.searchCompounds,
  // Since 2026-11-18 the search box also lists label-statement names; these tests cover compounds.
  searchNames: async (query: string) => ({ results: await apiMocks.searchCompounds(query), label_names: [] }),
  fetchInteraction: apiMocks.fetchInteraction,
  checkStack: apiMocks.checkStack,
}))

describe('App external links', () => {
  // Without this, every test's page stays in the document and later queries find duplicates.
  afterEach(cleanup)

  beforeEach(() => {
    apiMocks.fetchHealth.mockReset()
    apiMocks.fetchHealth.mockResolvedValue(defaultHealthResponse)

    apiMocks.fetchAllCompounds.mockReset()
    apiMocks.fetchAllCompounds.mockResolvedValue(defaultCompoundList)

    apiMocks.fetchInteractionsList.mockReset()
    apiMocks.fetchInteractionsList.mockResolvedValue(defaultInteractionsList)

    apiMocks.fetchLabelStatementsSummary.mockReset()
    apiMocks.fetchLabelStatementsSummary.mockResolvedValue({
      status: 'unavailable',
      disclaimer: 'FDA-approved label text, quoted verbatim, not reviewed or assessed by SuppTracker, not medical advice, absence of a statement does not mean a combination is safe.',
    })

    apiMocks.fetchLabelStatements.mockReset()
    apiMocks.fetchLabelStatements.mockResolvedValue({
      status: 'unavailable',
      disclaimer: 'FDA-approved label text, quoted verbatim, not reviewed or assessed by SuppTracker, not medical advice, absence of a statement does not mean a combination is safe.',
      total: 0,
      items: [],
    })

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

    apiMocks.fetchLabelStatementLookup.mockReset()
    apiMocks.fetchLabelStatementLookup.mockResolvedValue({
      status: 'unavailable',
      assessment: 'not_assessed',
      disclaimer: '',
      message: '',
      names: [],
      total_pairs: 0,
      truncated: false,
      pairs: [],
    })
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

  it('renders dataset external links provided as plain URLs', async () => {
    apiMocks.fetchAllCompounds.mockResolvedValueOnce([
      {
        id: 'berberine',
        name: 'Berberine',
        synonyms: [],
        external_links: 'https://example.com/berberine',
      } as unknown as Compound,
    ])

    render(<App />)

    const externalLink = await screen.findByRole('link', { name: 'Https://example.com/berberine' })
    expect(externalLink).toHaveAttribute('href', 'https://example.com/berberine')
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

  it('shows resolved stack items even when no interactions are found', async () => {
    apiMocks.checkStack.mockResolvedValueOnce({
      interactions: [],
      resolved_items: ['caffeine', 'ashwagandha'],
    })

    render(<App />)

    const textarea = await screen.findByLabelText(/supplement stack list/i)
    const form = textarea.closest('form') as HTMLFormElement
    const submitButton = within(form).getByRole('button', { name: /check stack/i })
    fireEvent.change(textarea, { target: { value: 'Caffeine, Ashwagandha' } })
    fireEvent.click(submitButton)

    expect(apiMocks.checkStack).toHaveBeenCalledWith(['Caffeine', 'Ashwagandha'])
    expect(await screen.findByText(/no assessed interactions were found in caffeine, ashwagandha/i)).toBeInTheDocument()
  })

  it('surfaces normalized stack names when the API omits interaction data', async () => {
    apiMocks.checkStack.mockResolvedValueOnce({
      resolved_items: ['caffeine', 'ashwagandha'],
    } as unknown as StackResponse)

    render(<App />)

    const textarea = await screen.findByLabelText(/supplement stack list/i)
    const form = textarea.closest('form') as HTMLFormElement
    const submitButton = within(form).getByRole('button', { name: /check stack/i })
    fireEvent.change(textarea, { target: { value: 'Caffeine, Ashwagandha' } })
    fireEvent.click(submitButton)

    expect(apiMocks.checkStack).toHaveBeenCalledWith(['Caffeine', 'Ashwagandha'])
    expect(await screen.findByText(/no assessed interactions were found in caffeine, ashwagandha/i)).toBeInTheDocument()
  })

  it('falls back to stack items when resolved names are missing', async () => {
    apiMocks.checkStack.mockResolvedValueOnce({
      interactions: null,
      items: ['caffeine', 'ashwagandha'],
    } as unknown as StackResponse)

    render(<App />)

    const textarea = await screen.findByLabelText(/supplement stack list/i)
    const form = textarea.closest('form') as HTMLFormElement
    const submitButton = within(form).getByRole('button', { name: /check stack/i })
    fireEvent.change(textarea, { target: { value: 'Caffeine, Ashwagandha' } })
    fireEvent.click(submitButton)

    expect(apiMocks.checkStack).toHaveBeenCalledWith(['Caffeine', 'Ashwagandha'])
    expect(await screen.findByText(/no assessed interactions were found in caffeine, ashwagandha/i)).toBeInTheDocument()
  })

  it('falls back to submitted names when neither resolved nor items are provided', async () => {
    apiMocks.checkStack.mockResolvedValueOnce({
      interactions: undefined,
    } as unknown as StackResponse)

    render(<App />)

    const textarea = await screen.findByLabelText(/supplement stack list/i)
    const form = textarea.closest('form') as HTMLFormElement
    const submitButton = within(form).getByRole('button', { name: /check stack/i })
    fireEvent.change(textarea, { target: { value: 'Rhodiola, Kava' } })
    fireEvent.click(submitButton)

    expect(apiMocks.checkStack).toHaveBeenCalledWith(['Rhodiola', 'Kava'])
    expect(await screen.findByText(/no assessed interactions were found in rhodiola, kava/i)).toBeInTheDocument()
  })

  it('uses cells as a fallback when interactions are omitted', async () => {
    apiMocks.checkStack.mockResolvedValueOnce({
      cells: [
        {
          a: 'caffeine',
          b: 'ashwagandha',
          severity: 'Mild',
          evidence: 'B',
          risk_score: 0.75,
        },
      ],
      resolved_items: ['caffeine', 'ashwagandha'],
    } as unknown as StackResponse)

    render(<App />)

    const textarea = await screen.findByLabelText(/supplement stack list/i)
    const form = textarea.closest('form') as HTMLFormElement
    const submitButton = within(form).getByRole('button', { name: /check stack/i })
    fireEvent.change(textarea, { target: { value: 'Caffeine, Ashwagandha' } })
    fireEvent.click(submitButton)

    expect(apiMocks.checkStack).toHaveBeenCalledWith(['Caffeine', 'Ashwagandha'])
    expect(await screen.findByText(/interactions found for caffeine, ashwagandha/i)).toBeInTheDocument()
    expect(screen.getByRole('table')).toBeInTheDocument()
  })

  const caffeineLookup = {
    status: 'available',
    assessment: 'not_assessed',
    disclaimer: 'FDA-approved label text, quoted verbatim.',
    message: 'FDA label statements name these together. This is quoted label text, not an assessment by SuppTracker.',
    names: [
      { input: 'caffeine', supplements: [{ supplement_id: 'caffeine', supplement_name: 'Caffeine', is_group_term: false, statements: 3 }], drug_total: 0, drugs: [] },
      { input: 'adenosine', supplements: [], drug_total: 1, drugs: [{ drug_id: 'adenosine', drug_names_raw: 'ADENOSINE', statements: 2 }] },
    ],
    total_pairs: 1,
    truncated: false,
    pairs: [
      {
        supplement_input: 'caffeine',
        drug_input: 'adenosine',
        supplement_id: 'caffeine',
        supplement_name: 'Caffeine',
        is_group_term: false,
        drug_id: 'adenosine',
        drug_names_raw: 'ADENOSINE',
        labels: 4,
        total: 1,
        items: [
          {
            statement_id: 'abc',
            sentence: 'A verbatim label sentence naming caffeine.',
            label_count: '4',
            label_url: 'https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=x',
          },
        ],
      },
    ],
  }

  it('shows label statements and an honest message when a pair is outside the assessed list', async () => {
    apiMocks.fetchInteraction.mockRejectedValueOnce(new Error('One or both compounds not found'))
    apiMocks.fetchLabelStatementLookup.mockResolvedValueOnce(caffeineLookup)

    render(<App />)

    fireEvent.change(await screen.findByLabelText('Compound A'), { target: { value: 'caffeine' } })
    fireEvent.change(screen.getByLabelText('Compound B'), { target: { value: 'adenosine' } })
    fireEvent.click(screen.getByRole('button', { name: /check pair/i }))

    expect(await screen.findByText(/nothing was assessed\. This does not mean the combination is safe\./i)).toBeInTheDocument()
    expect(apiMocks.fetchLabelStatementLookup).toHaveBeenCalledWith(['caffeine', 'adenosine'])
    expect(await screen.findByText('A verbatim label sentence naming caffeine.')).toBeInTheDocument()
    expect(screen.getByText(/not an assessment by SuppTracker/i)).toBeInTheDocument()
    expect(screen.queryByText(/no interaction/i)).not.toBeInTheDocument()
  })

  it('accepts semicolons in a stack and says plainly when no label statement matches', async () => {
    apiMocks.checkStack.mockResolvedValueOnce({ interactions: [], resolved_items: ['caffeine', 'aspirin'] })
    apiMocks.fetchLabelStatementLookup.mockResolvedValueOnce({
      ...caffeineLookup,
      message: 'No FDA label statement in this collection names these together. This does not mean the combination is safe.',
      names: [
        { input: 'caffeine', supplements: caffeineLookup.names[0].supplements, drug_total: 0, drugs: [] },
        { input: 'unobtainium', supplements: [], drug_total: 0, drugs: [] },
      ],
      total_pairs: 0,
      pairs: [],
    })

    render(<App />)

    const textarea = await screen.findByLabelText(/supplement stack list/i)
    const form = textarea.closest('form') as HTMLFormElement
    fireEvent.change(textarea, { target: { value: 'caffeine; unobtainium' } })
    fireEvent.click(within(form).getByRole('button', { name: /check stack/i }))

    expect(apiMocks.checkStack).toHaveBeenCalledWith(['caffeine', 'unobtainium'])
    expect(await screen.findByText(/No FDA label statement in this collection names these together\. This does not mean the combination is safe\./)).toBeInTheDocument()
    expect(screen.getByText(/Not named in the label statement collection: unobtainium\./)).toBeInTheDocument()
  })

  it('drops the pair answer and its label statements as soon as a name is edited', async () => {
    apiMocks.fetchInteraction.mockRejectedValueOnce(new Error('One or both compounds not found'))
    apiMocks.fetchLabelStatementLookup.mockResolvedValueOnce(caffeineLookup)

    render(<App />)

    fireEvent.change(await screen.findByLabelText('Compound A'), { target: { value: 'caffeine' } })
    fireEvent.change(screen.getByLabelText('Compound B'), { target: { value: 'adenosine' } })
    fireEvent.click(screen.getByRole('button', { name: /check pair/i }))
    expect(await screen.findByText('A verbatim label sentence naming caffeine.')).toBeInTheDocument()
    expect(screen.getByText(/nothing was assessed/i)).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Compound A'), { target: { value: 'caffeinex' } })

    // The names on screen are no longer the names that were checked.
    expect(screen.queryByText('A verbatim label sentence naming caffeine.')).not.toBeInTheDocument()
    expect(screen.queryByText(/nothing was assessed/i)).not.toBeInTheDocument()
  })

  it('ignores a pair reply that arrives after the names were edited', async () => {
    let reply: (value: unknown) => void = () => {}
    apiMocks.fetchInteraction.mockReturnValueOnce(
      new Promise((resolve) => {
        reply = resolve
      })
    )

    render(<App />)

    fireEvent.change(await screen.findByLabelText('Compound A'), { target: { value: 'caffeine' } })
    fireEvent.change(screen.getByLabelText('Compound B'), { target: { value: 'aspirin' } })
    fireEvent.click(screen.getByRole('button', { name: /check pair/i }))
    fireEvent.change(screen.getByLabelText('Compound A'), { target: { value: 'caffeine citrate' } })
    await act(async () => {
      reply({ assessment: 'not_assessed', message: 'A late reply for the earlier names.' })
    })

    expect(screen.queryByText('A late reply for the earlier names.')).not.toBeInTheDocument()
    expect(screen.queryByText(/checking interaction/i)).not.toBeInTheDocument()
  })

  it('clears stack results when the example is loaded or the list is edited', async () => {
    apiMocks.checkStack.mockResolvedValue({ interactions: [], resolved_items: ['caffeine', 'adenosine'] })
    apiMocks.fetchLabelStatementLookup.mockResolvedValue(caffeineLookup)

    render(<App />)

    const textarea = await screen.findByLabelText(/supplement stack list/i)
    const form = textarea.closest('form') as HTMLFormElement
    fireEvent.change(textarea, { target: { value: 'caffeine; adenosine' } })
    fireEvent.click(within(form).getByRole('button', { name: /check stack/i }))
    expect(await screen.findByText('A verbatim label sentence naming caffeine.')).toBeInTheDocument()
    expect(screen.getByText(/No assessed interactions were found in/)).toBeInTheDocument()

    fireEvent.click(within(form).getByRole('button', { name: /use example/i }))
    expect(screen.queryByText('A verbatim label sentence naming caffeine.')).not.toBeInTheDocument()
    expect(screen.queryByText(/No assessed interactions were found in/)).not.toBeInTheDocument()

    fireEvent.click(within(form).getByRole('button', { name: /check stack/i }))
    expect(await screen.findByText('A verbatim label sentence naming caffeine.')).toBeInTheDocument()
    fireEvent.change(textarea, { target: { value: 'caffeine; adenosine; zinc' } })
    expect(screen.queryByText('A verbatim label sentence naming caffeine.')).not.toBeInTheDocument()
  })

  it('does not leave an earlier stack result under a list that is too short', async () => {
    apiMocks.checkStack.mockResolvedValue({ interactions: [], resolved_items: ['caffeine', 'adenosine'] })
    apiMocks.fetchLabelStatementLookup.mockResolvedValue(caffeineLookup)

    render(<App />)

    const textarea = await screen.findByLabelText(/supplement stack list/i)
    const form = textarea.closest('form') as HTMLFormElement
    fireEvent.change(textarea, { target: { value: 'caffeine; adenosine' } })
    fireEvent.click(within(form).getByRole('button', { name: /check stack/i }))
    expect(await screen.findByText('A verbatim label sentence naming caffeine.')).toBeInTheDocument()

    fireEvent.change(textarea, { target: { value: 'caffeine' } })
    fireEvent.click(within(form).getByRole('button', { name: /check stack/i }))

    expect(await screen.findByText('List at least two compounds to evaluate the stack.')).toBeInTheDocument()
    expect(screen.queryByText('A verbatim label sentence naming caffeine.')).not.toBeInTheDocument()
  })

  it('removes the label statement note for an earlier search when the box is emptied', async () => {
    apiMocks.fetchLabelStatementLookup.mockResolvedValueOnce({
      ...caffeineLookup,
      message: '',
      names: [{ input: 'creatine', supplements: [], drug_total: 0, drugs: [] }],
      total_pairs: 0,
      pairs: [],
    })

    render(<App />)

    const input = await screen.findByLabelText('Compound search query')
    const form = input.closest('form') as HTMLFormElement
    fireEvent.change(input, { target: { value: 'creatine' } })
    fireEvent.submit(form)
    expect(await screen.findByText(/“creatine” is not named in the FDA label statement collection/)).toBeInTheDocument()

    fireEvent.change(input, { target: { value: '' } })
    fireEvent.submit(form)

    expect(await screen.findByText('Enter a compound name to search.')).toBeInTheDocument()
    expect(screen.queryByText(/“creatine” is not named/)).not.toBeInTheDocument()
  })

  it('always shows the not-medical-advice notice', async () => {
    render(<App />)

    const notice = await screen.findByRole('note')
    expect(notice).toHaveTextContent('It is not medical advice')
    expect(notice).toHaveTextContent('A missing result does not mean a combination is safe.')
  })

  it('shows the project notes search only where notes are available', async () => {
    const { unmount } = render(<App />)
    await screen.findByText(/None loaded: pair and stack checks/)
    expect(screen.queryByRole('heading', { name: 'Project notes search' })).not.toBeInTheDocument()
    unmount()

    apiMocks.fetchHealth.mockResolvedValue({ ...defaultHealthResponse, docs_indexed: 20 })
    render(<App />)
    expect(await screen.findByRole('heading', { name: 'Project notes search' })).toBeInTheDocument()
  })

  it('tells the reader when no interaction records are loaded', async () => {
    render(<App />)

    expect(await screen.findByText(/None loaded: pair and stack checks can only report "not assessed"/)).toBeInTheDocument()
    // With nothing assessed, the sources cannot be "powering recommendations".
    expect(screen.getByText('Loaded, but not yet cited by any assessed record')).toBeInTheDocument()
    expect(screen.queryByText('Citations powering recommendations')).not.toBeInTheDocument()
  })
})

describe('parseStackData', () => {
  test('throws error if < 2 compounds', () => {
    expect(() => parseStackData({}, ['A'])).toThrow(
      'List at least two compounds to evaluate the stack.',
    )
  })

  test('uses resolved_items first', () => {
    const result = parseStackData({ resolved_items: ['A', 'B'] }, [])
    expect(result.compounds).toEqual(['A', 'B'])
  })

  test('uses items if resolved_items missing', () => {
    const result = parseStackData({ items: ['A', 'B'] }, [])
    expect(result.compounds).toEqual(['A', 'B'])
  })

  test('falls back to user input', () => {
    const result = parseStackData({}, ['A', 'B'])
    expect(result.compounds).toEqual(['A', 'B'])
  })

  test('handles null/undefined interactions', () => {
    const result = parseStackData({ interactions: null }, ['A', 'B'])
    expect(result.interactions).toBeNull()

    const result2 = parseStackData({}, ['A', 'B'])
    expect(result2.interactions).toBeNull()
  })
})
