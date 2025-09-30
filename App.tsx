import React, { FormEvent, useMemo, useState } from 'react'
import './App.css'
import { checkStack, fetchInteraction, searchCompounds } from './api'
import type {
  Compound,
  InteractionResponse,
  InteractionRecord,
  Source,
  StackInteraction,
} from './types'

// Types
type AsyncStatus = 'idle' | 'loading' | 'success' | 'error'

// Constants
const DEFAULT_STACK_EXAMPLE = 'creatine, caffeine, magnesium'

// Utils
function parseStackInput(value: string): string[] {
  return value
    .split(/[\n,]+/)
    .map((token) => token.trim())
    .filter(Boolean)
}

function sourceLabel(source: Source, index: number): string {
  return (
    source.citation ||
    source.title ||
    source.reference ||
    source.url ||
    source.id ||
    `Source ${index + 1}`
  )
}

function resolveSources(interaction: InteractionRecord | null | undefined): Source[] {
  if (!interaction) return []
  return Array.isArray(interaction.sources) ? interaction.sources : []
}

function severityClass(severity: string | null | undefined): string {
  const normalized = (severity || 'unknown').toLowerCase()
  return `badge badge-${normalized}`
}

export default function App(): JSX.Element {
  // Search state
  const [query, setQuery] = useState<string>('')
  const [searchStatus, setSearchStatus] = useState<AsyncStatus>('idle')
  const [searchResults, setSearchResults] = useState<Compound[]>([])
  const [searchError, setSearchError] = useState<string | null>(null)

  // Pair checker state
  const [pairA, setPairA] = useState<string>('')
  const [pairB, setPairB] = useState<string>('')
  const [pairStatus, setPairStatus] = useState<AsyncStatus>('idle')
  const [pairError, setPairError] = useState<string | null>(null)
  const [pairData, setPairData] = useState<InteractionResponse | null>(null)

  // Stack checker state
  const [stackText, setStackText] = useState<string>(DEFAULT_STACK_EXAMPLE)
  const [stackStatus, setStackStatus] = useState<AsyncStatus>('idle')
  const [stackError, setStackError] = useState<string | null>(null)
  const [stackInteractions, setStackInteractions] = useState<StackInteraction[] | null>(null)
  const [stackCompounds, setStackCompounds] = useState<string[]>([])

  const hasSearchResults = searchResults.length > 0
  const stackHasInteractions = !!stackInteractions && stackInteractions.length > 0

  // Lookup for compound names
  const compoundLookup = useMemo(() => {
    return searchResults.reduce<Record<string, Compound>>((acc, compound) => {
      acc[compound.id] = compound
      return acc
    }, {})
  }, [searchResults])

  // Handlers
  async function handleSearch(event?: FormEvent<HTMLFormElement>): Promise<void> {
    event?.preventDefault()
    const trimmed = query.trim()
    if (!trimmed) {
      setSearchResults([])
      setSearchStatus('idle')
      setSearchError('Enter a compound name to search.')
      return
    }

    setSearchStatus('loading')
    setSearchError(null)
    try {
      const results = await searchCompounds(trimmed)
      setSearchResults(results)
      setSearchStatus('success')
      if (results.length === 0) {
        setSearchError('No compounds matched your search.')
      }
    } catch (error) {
      setSearchStatus('error')
      setSearchResults([])
      setSearchError(error instanceof Error ? error.message : 'Search failed')
    }
  }

  async function handlePairSubmit(event?: FormEvent<HTMLFormElement>): Promise<void> {
    event?.preventDefault()
    const a = pairA.trim()
    const b = pairB.trim()
    if (!a || !b) {
      setPairStatus('error')
      setPairData(null)
      setPairError('Enter two compounds to run a pair check.')
      return
    }

    setPairStatus('loading')
    setPairError(null)
    try {
      const data = await fetchInteraction(a, b)
      setPairData(data)
      setPairStatus('success')
    } catch (error) {
      setPairData(null)
      setPairStatus('error')
      setPairError(error instanceof Error ? error.message : 'Interaction lookup failed')
    }
  }

  async function handleStackSubmit(event?: FormEvent<HTMLFormElement>): Promise<void> {
    event?.preventDefault()
    const compounds = parseStackInput(stackText)
    if (compounds.length === 0) {
      setStackStatus('error')
      setStackInteractions(null)
      setStackCompounds([])
      setStackError('List at least one compound to evaluate the stack.')
      return
    }

    setStackStatus('loading')
    setStackError(null)
    try {
      const data = await checkStack(compounds)
      setStackInteractions(data.interactions)
      setStackCompounds(compounds)
      setStackStatus('success')
      setStackError(null)
    } catch (error) {
      setStackInteractions(null)
      setStackCompounds([])
      setStackStatus('error')
      setStackError(error instanceof Error ? error.message : 'Stack check failed')
    }
  }

  // Derived values
  const interaction = pairData?.interaction
  const pairSources = resolveSources(interaction)
  const riskScore = interaction?.score
  const formattedRiskScore = typeof riskScore === 'number' ? riskScore.toFixed(2) : 'N/A'
  const pairHeading = pairData?.pair
    ? `${pairData.pair.a || 'Compound A'} × ${pairData.pair.b || 'Compound B'}`
    : 'Selected pair'

  return (
    <div className="app-shell">
      <header className="app-header">
        <h1>Supplement Interaction Tracker</h1>
        <p className="app-tagline">
          Search compounds, review pair interactions, and evaluate supplement stacks.
        </p>
      </header>

      <main className="grid">
        {/* Search */}
        <section className="card">
          <div className="card-header">
            <h2 id="search-heading">Search compounds</h2>
            <p>Use names or synonyms to locate supplements in the dataset.</p>
          </div>

          <form className="stacked" aria-labelledby="search-heading" onSubmit={handleSearch}>
            <label className="sr-only" htmlFor="search-input">Compound search query</label>
            <div className="input-row">
              <input
                id="search-input"
                type="text"
                value={query}
                onChange={(event) => {
                  setQuery(event.target.value)
                  if (searchError) setSearchError(null)
                }}
                placeholder="e.g. creatine"
                autoComplete="off"
                aria-describedby={searchError ? 'search-error' : undefined}
              />
              <button className="primary" type="submit">Search</button>
            </div>
          </form>

          {searchStatus === 'loading' && <p className="status" role="status" aria-live="polite">Searching…</p>}
          {searchError && (
            <p id="search-error" className="status status-error" role="alert" aria-live="assertive">
              {searchError}
            </p>
          )}
          {hasSearchResults && (
            <ul aria-live="polite" className="pill-grid">
              {searchResults.map((compound) => (
                <li className="pill" key={compound.id}>
                  <span className="pill-name">{compound.name}</span>
                  {compound.synonyms.length > 0 && (
                    <span className="pill-meta">Also known as {compound.synonyms.join(', ')}</span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* Pair checker */}
        <section className="card">
          <div className="card-header">
            <h2 id="pair-heading">Pair checker</h2>
            <p>Validate two compounds before combining them.</p>
          </div>

          <form className="stacked" aria-labelledby="pair-heading" onSubmit={handlePairSubmit}>
            <div className="pair-inputs">
              <label className="sr-only" htmlFor="pair-a">Compound A</label>
              <input
                id="pair-a"
                type="text"
                value={pairA}
                onChange={(event) => {
                  setPairA(event.target.value)
                  if (pairError) setPairError(null)
                }}
                placeholder="First compound"
                autoComplete="off"
              />
              <span aria-hidden="true" className="pair-separator">×</span>
              <label className="sr-only" htmlFor="pair-b">Compound B</label>
              <input
                id="pair-b"
                type="text"
                value={pairB}
                onChange={(event) => {
                  setPairB(event.target.value)
                  if (pairError) setPairError(null)
                }}
                placeholder="Second compound"
                autoComplete="off"
              />
              <button className="primary" type="submit">Check pair</button>
            </div>
          </form>

          {pairStatus === 'loading' && <p className="status" role="status" aria-live="polite">Checking interaction…</p>}
          {pairError && <p className="status status-error" role="alert" aria-live="assertive">{pairError}</p>}

          {interaction && pairStatus === 'success' && (
            <div aria-live="polite" className="pair-result">
              <h3 className="pair-title">{pairHeading}</h3>
              <div className="badges">
                <span className={severityClass(interaction.severity)}>Severity: {interaction.severity}</span>
                <span className="badge badge-evidence">Evidence grade: {interaction.evidence_grade}</span>
                <span className="badge badge-muted">Risk score: {formattedRiskScore}</span>
              </div>
              <dl className="description">
                <div>
                  <dt>Effect</dt>
                  <dd>{interaction.effect}</dd>
                </div>
                <div>
                  <dt>Recommended action</dt>
                  <dd>{interaction.action_resolved || interaction.action}</dd>
                </div>
              </dl>
              <details className="sources">
                <summary>Evidence sources ({pairSources.length})</summary>
                <ul>
                  {pairSources.length === 0 && <li>No citations provided.</li>}
                  {pairSources.map((source, index) => (
                    <li key={source.id ?? `${index}`}>{sourceLabel(source, index)}</li>
                  ))}
                </ul>
              </details>
            </div>
          )}
        </section>

        {/* Stack checker */}
        <section className="card">
          <div className="card-header">
            <h2 id="stack-heading">Stack checker</h2>
            <p>Paste a stack to identify riskier combinations.</p>
          </div>

          <form className="stacked" aria-labelledby="stack-heading" onSubmit={handleStackSubmit}>
            <label className="sr-only" htmlFor="stack-input">Supplement stack list</label>
            <textarea
              id="stack-input"
              rows={4}
              value={stackText}
              onChange={(event) => {
                setStackText(event.target.value)
                if (stackError) setStackError(null)
              }}
              placeholder={DEFAULT_STACK_EXAMPLE}
            />
            <div className="actions">
              <button className="primary" type="submit">Check stack</button>
              <button
                type="button"
                onClick={() => setStackText(DEFAULT_STACK_EXAMPLE)}
                className="ghost"
              >
                Use example
              </button>
            </div>
          </form>

          {stackStatus === 'loading' && <p className="status" role="status" aria-live="polite">Evaluating stack…</p>}
          {stackError && (
            <p className="status status-error" role="alert" aria-live="assertive">{stackError}</p>
          )}

          {stackStatus === 'success' && stackInteractions && (
            <div aria-live="polite" className="stack-results">
              <h3>
                {stackHasInteractions
                  ? `Interactions found for ${stackCompounds.join(', ')}`
                  : 'No interactions detected in this stack'}
              </h3>

              {stackHasInteractions && (
                <table>
                  <thead>
                    <tr>
                      <th scope="col">Compound A</th>
                      <th scope="col">Compound B</th>
                      <th scope="col">Severity</th>
                      <th scope="col">Evidence</th>
                      <th scope="col">Risk</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stackInteractions.map((interaction, index) => (
                      <tr key={`${interaction.a}-${interaction.b}-${index}`}>
                        <td>{compoundLookup[interaction.a]?.name ?? interaction.a}</td>
                        <td>{compoundLookup[interaction.b]?.name ?? interaction.b}</td>
                        <td>
                          <span className={severityClass(interaction.severity)}>{interaction.severity}</span>
                        </td>
                        <td>{interaction.evidence}</td>
                        <td>{interaction.score.toFixed(2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}
        </section>
      </main>
    </div>
  )
}
