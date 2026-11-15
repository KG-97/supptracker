import { FormEvent, useEffect, useState } from 'react'
import {
  fetchLabelStatements,
  fetchLabelStatementsSummary,
} from './api'
import type {
  LabelStatement,
  LabelStatementsSummary,
} from './api'

const DEFAULT_DISCLAIMER =
  'FDA-approved label text, quoted verbatim, not reviewed or assessed by SuppTracker, not medical advice, absence of a statement does not mean a combination is safe.'

const NOT_ASSESSED_MESSAGE =
  'Not assessed. No FDA label statement was found for this search. This does not mean the combination is safe.'

const UNAVAILABLE_MESSAGE =
  'FDA label statements are unavailable. Nothing has been assessed.'

function formatEffectiveTime(value: string): string {
  const compactDate = value.match(/^(\d{4})(\d{2})(\d{2})/)
  if (compactDate) {
    return `${compactDate[1]}-${compactDate[2]}-${compactDate[3]}`
  }

  const hyphenatedDate = value.match(/^(\d{4}-\d{2}-\d{2})/)
  return hyphenatedDate ? hyphenatedDate[1] : value
}

function labelCountText(item: LabelStatement): string {
  const count = Number(item.label_count)
  return `appears in ${item.label_count} ${count === 1 ? 'label' : 'labels'}`
}

export default function LabelStatements() {
  const [summary, setSummary] = useState<LabelStatementsSummary | null>(null)
  const [disclaimer, setDisclaimer] = useState(DEFAULT_DISCLAIMER)
  const [supplement, setSupplement] = useState('')
  const [drug, setDrug] = useState('')
  const [query, setQuery] = useState('')
  const [items, setItems] = useState<LabelStatement[]>([])
  const [total, setTotal] = useState(0)
  const [availability, setAvailability] = useState<'loading' | 'available' | 'unavailable'>('loading')
  const [isLoadingResults, setIsLoadingResults] = useState(false)

  async function loadResults(offset = 0, append = false) {
    setIsLoadingResults(true)

    try {
      const response = await fetchLabelStatements({
        supplement: supplement || undefined,
        drug: drug || undefined,
        q: query || undefined,
        limit: 25,
        offset,
      })

      setDisclaimer(response.disclaimer || DEFAULT_DISCLAIMER)

      if (response.status !== 'available') {
        setItems([])
        setTotal(0)
        setAvailability('unavailable')
        return
      }

      setItems((currentItems) => (append ? [...currentItems, ...response.items] : response.items))
      setTotal(response.total)
      setAvailability('available')
    } catch {
      setItems([])
      setTotal(0)
      setAvailability('unavailable')
    } finally {
      setIsLoadingResults(false)
    }
  }

  useEffect(() => {
    let active = true

    async function loadSummary() {
      try {
        const response = await fetchLabelStatementsSummary()

        if (!active) {
          return
        }

        setDisclaimer(response.disclaimer || DEFAULT_DISCLAIMER)

        if (response.status !== 'available') {
          setSummary(null)
          setItems([])
          setTotal(0)
          setAvailability('unavailable')
          return
        }

        setSummary(response)
        setAvailability('available')
        await loadResults()
      } catch {
        if (!active) {
          return
        }

        setSummary(null)
        setItems([])
        setTotal(0)
        setAvailability('unavailable')
      }
    }

    void loadSummary()

    return () => {
      active = false
    }
  }, [])

  function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    void loadResults()
  }

  return (
    <section className="card full-width label-statements" aria-labelledby="label-statements-heading">
      <div className="card-header">
        <h2 id="label-statements-heading">FDA label statements</h2>
        <p>Verbatim sentences from FDA-approved drug labels.</p>
      </div>

      <div
        className="label-statements-disclaimer"
        role="region"
        aria-label="FDA label statements disclaimer"
      >
        <p>{disclaimer}</p>
      </div>

      {availability === 'unavailable' ? (
        <p className="status" role="status">
          {UNAVAILABLE_MESSAGE}
        </p>
      ) : (
        <>
          {summary && (
            <>
              <ul className="stat-grid label-statement-counts" aria-label="FDA label statement corpus counts">
                <li className="stat">
                  <span className="stat-label">Statements</span>
                  <strong className="stat-value">{summary.counts.statements}</strong>
                </li>
                <li className="stat">
                  <span className="stat-label">Pairs</span>
                  <strong className="stat-value">{summary.counts.pairs}</strong>
                </li>
                <li className="stat">
                  <span className="stat-label">Supplements</span>
                  <strong className="stat-value">{summary.counts.supplements}</strong>
                </li>
                <li className="stat">
                  <span className="stat-label">Drugs</span>
                  <strong className="stat-value">{summary.counts.drugs}</strong>
                </li>
              </ul>

              <p className="label-statements-source">
                Source:{' '}
                {summary.source ? (
                  <a href={summary.source} target="_blank" rel="noopener noreferrer">
                    openFDA drug label API
                  </a>
                ) : (
                  'openFDA drug label API'
                )}
                {' · '}Licence:{' '}
                {summary.license_url ? (
                  <a href={summary.license_url} target="_blank" rel="noopener noreferrer">
                    {summary.license}
                  </a>
                ) : (
                  summary.license
                )}
              </p>

              <form onSubmit={handleSearch} className="label-statements-filters">
                <div>
                  <label htmlFor="label-statements-supplement">Supplement</label>
                  <select
                    id="label-statements-supplement"
                    value={supplement}
                    onChange={(event) => setSupplement(event.target.value)}
                  >
                    <option value="">All supplements</option>
                    {summary.supplements.map((option) => (
                      <option key={option.supplement_id} value={option.supplement_id}>
                        {option.supplement_name}
                        {option.is_group_term ? ' (group term)' : ''}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label htmlFor="label-statements-drug">Drug</label>
                  <input
                    id="label-statements-drug"
                    value={drug}
                    onChange={(event) => setDrug(event.target.value)}
                    autoComplete="off"
                  />
                </div>

                <div>
                  <label htmlFor="label-statements-search">Text search</label>
                  <input
                    id="label-statements-search"
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    autoComplete="off"
                  />
                </div>

                <button type="submit" className="primary">
                  Search FDA label statements
                </button>
              </form>
            </>
          )}

          {isLoadingResults && <p className="status">Loading FDA label statements…</p>}

          {!isLoadingResults && summary && items.length === 0 && (
            <p className="status" role="status">
              {NOT_ASSESSED_MESSAGE}
            </p>
          )}

          {items.length > 0 && (
            <>
              <p className="label-statements-source" role="status">
                Showing {items.length} of {total} statements
              </p>
              <ul className="label-statement-list" aria-live="polite">
                {items.map((item) => (
                  <li key={item.statement_id} className="label-statement">
                    <q data-testid={`label-statement-sentence-${item.statement_id}`}>
                      {item.sentence}
                    </q>

                    <dl>
                      <div>
                        <dt>Supplement</dt>
                        <dd>
                          {item.supplement_name}{' '}
                          {item.is_group_term && <span className="badge label-group-term">group term</span>}
                        </dd>
                      </div>
                      <div>
                        <dt>Drug names</dt>
                        <dd>{item.drug_names_raw}</dd>
                      </div>
                      <div>
                        <dt>Label coverage</dt>
                        <dd>{labelCountText(item)}</dd>
                      </div>
                      <div>
                        <dt>Label date</dt>
                        <dd>{formatEffectiveTime(item.effective_time)}</dd>
                      </div>
                    </dl>

                    <a
                      href={item.label_url}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      View label on DailyMed
                    </a>
                  </li>
                ))}
              </ul>

              {items.length < total && (
                <button
                  type="button"
                  className="ghost"
                  onClick={() => void loadResults(items.length, true)}
                  disabled={isLoadingResults}
                >
                  Show more
                </button>
              )}
            </>
          )}
        </>
      )}
    </section>
  )
}
