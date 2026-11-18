import React, { FormEvent, useEffect, useMemo, useRef, useState } from 'react'
import './App.css'
import LabelStatements from './LabelStatements'
import type { LabelStatementsRequest } from './LabelStatements'
import LabelStatementMatches, { LabelStatementNameHits } from './LabelStatementMatches'
import {
  checkStack,
  fetchAllCompounds,
  fetchHealth,
  fetchInteraction,
  fetchInteractionsList,
  searchCompounds,
  searchDocuments,
} from '../api'
import type {
  Compound,
  ExternalLink,
  HealthResponse,
  InteractionResponse,
  InteractionWithRisk,
  Source,
  StackInteraction,
  DocumentSearchMeta,
  DocumentSearchResult,
} from '../types'

// Helper function to resolve sources from API response
function resolveSources(response: InteractionResponse | null): Source[] {
  if (!response) {
    return []
  }

  const detailedSources = response.sources ?? []
  if (detailedSources.length > 0) {
    return detailedSources
  }

  const interactionSources = response.interaction?.sources ?? []
  return interactionSources.map((sourceId, index) => ({
    id: sourceId,
    title: `Source ${index + 1}`,
  }))
}

type AsyncStatus = 'idle' | 'loading' | 'success' | 'error'

export const DEFAULT_STACK_EXAMPLE = 'caffeine, aspirin'

export function parseStackData(apiData: any, userCompounds: string[]) {
  const compounds = apiData?.evaluated_items ?? apiData?.resolved_items ?? apiData?.items ?? userCompounds
  const interactions = apiData?.interactions ?? apiData?.cells ?? null

  if (!compounds || (compounds.length < 2 && !Array.isArray(apiData?.evaluated_items))) {
    throw new Error('List at least two compounds to evaluate the stack.')
  }

  return { compounds, interactions }
}

// The API answers 404 for a name outside the assessed compound list. Say what that means
// instead of leaving a bare "not found".
function explainLookupError(message: string): string {
  if (/not found|not recognised/i.test(message)) {
    return `${message.replace(/\.$/, '')}. Check the spelling: a name SuppTracker does not recognise cannot be checked, so nothing was assessed. This does not mean the combination is safe.`
  }
  return message
}

function parseStackInput(value: string): string[] {
  return value
    .split(/[\n,;]+/)
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

function severityClass(severity: string): string {
  const normalized = severity?.toLowerCase() || 'unknown'
  return `badge badge-${normalized}`
}

function formatDose(compound: Compound): string {
  const amount =
    typeof compound.typicalDoseAmount === 'string'
      ? compound.typicalDoseAmount.trim()
      : compound.typicalDoseAmount
  const unit =
    typeof compound.typicalDoseUnit === 'string'
      ? compound.typicalDoseUnit.trim()
      : compound.typicalDoseUnit

  if (amount && unit) {
    return `${amount} ${unit}`
  }

  if (amount || unit) {
    return (amount || unit) ?? 'Not specified'
  }

  const rawDoseCandidates: unknown[] = [
    compound.dose,
    (compound as Record<string, unknown>).doseGuide,
    (compound as Record<string, unknown>).dose_guide,
    (compound as Record<string, unknown>).dosage,
    (compound as Record<string, unknown>).dose_notes,
  ]

  for (const candidate of rawDoseCandidates) {
    if (typeof candidate === 'string') {
      const trimmed = candidate.trim()
      if (trimmed) {
        return trimmed
      }
    }
  }

  return 'Not specified'
}

function formatSourceKey(key: string): string {
  return key
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

function normaliseSynonyms(compound: Compound): string[] {
  const seen = new Set<string>()
  const synonyms: string[] = []

  const addValue = (value: string | null | undefined) => {
    if (!value) {
      return
    }
    const trimmed = value.trim()
    if (!trimmed) {
      return
    }
    const key = trimmed.toLowerCase()
    if (seen.has(key)) {
      return
    }
    seen.add(key)
    synonyms.push(trimmed)
  }

  const parseCandidate = (candidate: unknown) => {
    if (!candidate) {
      return
    }
    if (Array.isArray(candidate)) {
      for (const entry of candidate) {
        if (typeof entry === 'string') {
          addValue(entry)
        }
      }
      return
    }
    if (typeof candidate === 'string') {
      const parts = candidate
        .split(/[,;|\/]+/)
        .map((part) => part.trim())
        .filter(Boolean)
      if (parts.length === 0) {
        addValue(candidate)
      } else {
        parts.forEach(addValue)
      }
    }
  }

  parseCandidate(compound.synonyms)
  const record = compound as Record<string, unknown>
  parseCandidate(record.synonym)
  parseCandidate(record.synonyms_string)
  parseCandidate(record.synonym_list)
  parseCandidate(record.alternate_names)
  parseCandidate(record.also_known_as)

  return synonyms
}

function formatDocumentScore(score: number | undefined): string {
  if (typeof score !== 'number' || Number.isNaN(score)) {
    return '—'
  }
  const rounded = score >= 1 ? score.toFixed(2) : score.toFixed(3)
  return rounded
}

type NormalisedExternalLink = { label?: string; identifier?: string; url: string }

function parseExternalLinksValue(value: unknown): NormalisedExternalLink[] {
  if (!value) {
    return []
  }

  if (Array.isArray(value)) {
    return value.flatMap((item) => parseExternalLinksValue(item))
  }

  if (typeof value === 'string') {
    const trimmed = value.trim()
    if (!trimmed) {
      return []
    }

    try {
      const parsed = JSON.parse(trimmed)
      return parseExternalLinksValue(parsed)
    } catch {
      const entries = trimmed
        .split(/[;\n]+/)
        .map((segment) => segment.trim())
        .filter(Boolean)
      const links: NormalisedExternalLink[] = []
      for (const entry of entries) {
        const separator = entry.includes('|') ? '|' : entry.includes(',') ? ',' : null
        if (!separator) {
          const looksLikeUrl = /^[a-z][a-z0-9+.-]*:\/\//i.test(entry) || entry.startsWith('www.')
          if (looksLikeUrl) {
            links.push({ url: entry })
          }
          continue
        }
        const [rawLabel, rawUrl] = entry.split(separator, 2)
        const url = rawUrl?.trim()
        if (!url) {
          continue
        }
        const label = rawLabel?.trim()
        links.push({ url, ...(label ? { label } : {}) })
      }
      return links
    }
  }

  if (typeof value === 'object') {
    const record = value as ExternalLink & Record<string, unknown>
    if (record && Object.keys(record).length > 0) {
      const looksLikeLinkObject =
        typeof record.url === 'string' ||
        typeof (record as Record<string, unknown>).href === 'string' ||
        typeof (record as Record<string, unknown>).link === 'string'

      if (!looksLikeLinkObject) {
        const aggregated: NormalisedExternalLink[] = []
        for (const [key, entry] of Object.entries(record)) {
          if (typeof entry === 'string') {
            const trimmed = entry.trim()
            if (!trimmed) {
              continue
            }
            const identifier = typeof key === 'string' ? key.trim() : undefined
            const label = identifier ? formatSourceKey(identifier) : undefined
            aggregated.push({
              url: trimmed,
              ...(identifier ? { identifier } : {}),
              ...(label ? { label } : {}),
            })
            continue
          }

          const nestedLinks = parseExternalLinksValue(entry)
          for (const nested of nestedLinks) {
            const identifier =
              nested.identifier ?? (typeof key === 'string' ? key.trim() : undefined)
            const label =
              nested.label ??
              (typeof key === 'string' ? formatSourceKey(key.trim()) : undefined)
            aggregated.push({
              url: nested.url,
              ...(identifier ? { identifier } : {}),
              ...(label ? { label } : {}),
            })
          }
        }

        if (aggregated.length > 0) {
          return aggregated
        }
      }
    }

    const urlCandidate =
      (typeof record.url === 'string' && record.url.trim()) ||
      (typeof (record as Record<string, unknown>).href === 'string'
        ? ((record as Record<string, unknown>).href as string).trim()
        : undefined) ||
      (typeof (record as Record<string, unknown>).link === 'string'
        ? ((record as Record<string, unknown>).link as string).trim()
        : undefined)

    if (!urlCandidate) {
      return []
    }

    const labelCandidate =
      (typeof record.label === 'string' && record.label.trim()) ||
      (typeof (record as Record<string, unknown>).title === 'string'
        ? ((record as Record<string, unknown>).title as string).trim()
        : undefined) ||
      (typeof (record as Record<string, unknown>).name === 'string'
        ? ((record as Record<string, unknown>).name as string).trim()
        : undefined)

    const identifierCandidate =
      (typeof record.identifier === 'string' && record.identifier.trim()) ||
      (typeof (record as Record<string, unknown>).id === 'string'
        ? ((record as Record<string, unknown>).id as string).trim()
        : undefined) ||
      (typeof (record as Record<string, unknown>).slug === 'string'
        ? ((record as Record<string, unknown>).slug as string).trim()
        : undefined) ||
      (typeof (record as Record<string, unknown>).key === 'string'
        ? ((record as Record<string, unknown>).key as string).trim()
        : undefined)

    const link: NormalisedExternalLink = { url: urlCandidate }
    if (labelCandidate) {
      link.label = labelCandidate
    }
    if (identifierCandidate) {
      link.identifier = identifierCandidate
    }
    return [link]
  }

  return []
}

function lookupExternalId(ids: Record<string, string>, key: string): string | undefined {
  if (key in ids) {
    return ids[key]
  }
  const lowerKey = key.toLowerCase()
  if (lowerKey in ids) {
    return ids[lowerKey]
  }

  const normalised = lowerKey.replace(/[^a-z0-9]/g, '')
  for (const [candidateKey, value] of Object.entries(ids)) {
    if (
      candidateKey === key ||
      candidateKey.toLowerCase() === lowerKey ||
      candidateKey.toLowerCase().replace(/[^a-z0-9]/g, '') === normalised
    ) {
      return value
    }
  }

  return undefined
}

function compoundExternalLinks(
  compound: Compound
): { key: string; label: string; href: string }[] {
  const urls = compound.referenceUrls ?? {}
  const ids = compound.externalIds ?? {}
  const links: { key: string; label: string; href: string }[] = []
  const seen = new Map<string, number>()

  function addLink(key: string, label: string, href: string) {
    const trimmedHref = href.trim()
    if (!trimmedHref) {
      return
    }
    const hrefKey = trimmedHref.toLowerCase()
    if (seen.has(hrefKey)) {
      const index = seen.get(hrefKey) ?? -1
      if (index >= 0 && !links[index].label && label) {
        links[index] = { ...links[index], label }
      }
      return
    }
    seen.set(hrefKey, links.length)
    links.push({ key, label, href: trimmedHref })
  }

  for (const [key, href] of Object.entries(urls)) {
    if (typeof href !== 'string') {
      continue
    }
    const identifier = lookupExternalId(ids, key)
    const labelBase = formatSourceKey(key)
    const label = identifier ? `${labelBase} (${identifier})` : labelBase
    addLink(key, label, href)
  }

  const externalLinkValues = [
    compound.externalLinks,
    (compound as Record<string, unknown>).external_links,
  ]

  for (const value of externalLinkValues) {
    for (const entry of parseExternalLinksValue(value)) {
      const href = entry.url
      const label = entry.label?.trim() || entry.identifier?.trim() || formatSourceKey(entry.url)
      const key = entry.identifier?.trim() || entry.label?.trim() || entry.url
      addLink(key, label, href)
    }
  }

  return links
}

export default function App(): React.JSX.Element {
  const [query, setQuery] = useState('')
  const [searchStatus, setSearchStatus] = useState<AsyncStatus>('idle')
  const [searchResults, setSearchResults] = useState<Compound[]>([])
  const [searchError, setSearchError] = useState<string | null>(null)

  const [docQuery, setDocQuery] = useState('')
  const [docStatus, setDocStatus] = useState<AsyncStatus>('idle')
  const [docResults, setDocResults] = useState<DocumentSearchResult[]>([])
  const [docError, setDocError] = useState<string | null>(null)
  const [docMeta, setDocMeta] = useState<DocumentSearchMeta | null>(null)

  const [pairA, setPairA] = useState('')
  const [pairB, setPairB] = useState('')
  const [pairStatus, setPairStatus] = useState<AsyncStatus>('idle')
  const [pairError, setPairError] = useState<string | null>(null)
  const [pairData, setPairData] = useState<InteractionResponse | null>(null)

  const [stackText, setStackText] = useState(DEFAULT_STACK_EXAMPLE)
  const [stackStatus, setStackStatus] = useState<AsyncStatus>('idle')
  const [stackError, setStackError] = useState<string | null>(null)
  const [stackInteractions, setStackInteractions] = useState<StackInteraction[] | null>(null)
  const [stackCompounds, setStackCompounds] = useState<string[]>([])
  const [stackCoverage, setStackCoverage] = useState<{ total_pairs: number; assessed_pairs: number; not_assessed_pairs: number } | null>(null)

  const [pairLookup, setPairLookup] = useState<{ names: string[]; id: number }>({ names: [], id: 0 })
  const [stackLookup, setStackLookup] = useState<{ names: string[]; id: number }>({ names: [], id: 0 })
  const [searchLookup, setSearchLookup] = useState<{ name: string; id: number }>({ name: '', id: 0 })
  const [labelRequest, setLabelRequest] = useState<LabelStatementsRequest | null>(null)
  // Each check gets a number. A reply is ignored once a newer check has started or the
  // names it was made for have been edited.
  const searchRequest = useRef(0)
  const pairRequest = useRef(0)
  const stackRequest = useRef(0)

  const [overviewStatus, setOverviewStatus] = useState<AsyncStatus>('loading')
  const [overviewError, setOverviewError] = useState<string | null>(null)
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [allCompounds, setAllCompounds] = useState<Compound[]>([])
  const [allInteractions, setAllInteractions] = useState<InteractionWithRisk[]>([])

  useEffect(() => {
    async function loadDataset() {
      setOverviewStatus('loading')
      setOverviewError(null)
      try {
        const [healthResponse, compoundsResponse, interactionsResponse] = await Promise.all([
          fetchHealth(),
          fetchAllCompounds(),
          fetchInteractionsList(),
        ])

        setHealth(healthResponse)
        setAllCompounds(compoundsResponse)
        setAllInteractions(interactionsResponse)
        setOverviewStatus('success')
      } catch (error) {
        setOverviewStatus('error')
        setOverviewError(error instanceof Error ? error.message : 'Failed to load dataset overview')
      }
    }

    loadDataset()
  }, [])

  const hasSearchResults = searchResults.length > 0
  const hasDocResults = docResults.length > 0
  const stackHasInteractions = !!stackInteractions && stackInteractions.length > 0

  const compoundLookup = useMemo(() => {
    return searchResults.reduce<Record<string, Compound>>((acc, compound) => {
      acc[compound.id] = compound
      return acc
    }, {})
  }, [searchResults])

  const datasetCompoundLookup = useMemo(() => {
    return allCompounds.reduce<Record<string, Compound>>((acc, compound) => {
      acc[compound.id] = compound
      return acc
    }, {})
  }, [allCompounds])

  const stackCompoundLabels = useMemo(() => {
    return stackCompounds.map((compound) => {
      return (
        datasetCompoundLookup[compound]?.name ??
        compoundLookup[compound]?.name ??
        compound
      )
    })
  }, [stackCompounds, datasetCompoundLookup, compoundLookup])

  const shouldShowStackResults =
    stackStatus === 'success' && (stackInteractions !== null || stackCompoundLabels.length > 0)

  const topInteractions = useMemo(() => {
    const severityRanking: Record<string, number> = {
      severe: 3,
      moderate: 2,
      mild: 1,
      none: 0,
    }

    return [...allInteractions]
      .sort((a, b) => {
        const severityDelta = (severityRanking[b.severity.toLowerCase()] ?? 0) - (severityRanking[a.severity.toLowerCase()] ?? 0)
        if (severityDelta !== 0) {
          return severityDelta
        }
        return (b.risk_score ?? 0) - (a.risk_score ?? 0)
      })
      .slice(0, 4)
  }, [allInteractions])

  // Results describe the names that were submitted. Once those names are edited or fail
  // validation, drop the results so the page never shows an answer for other inputs.
  function clearPairResults() {
    pairRequest.current += 1
    setPairStatus('idle')
    setPairError(null)
    setPairData(null)
    setPairLookup((previous) =>
      previous.names.length === 0 ? previous : { names: [], id: previous.id + 1 }
    )
  }

  function clearStackResults() {
    stackRequest.current += 1
    setStackStatus('idle')
    setStackError(null)
    setStackInteractions(null)
    setStackCompounds((previous) => (previous.length === 0 ? previous : []))
    setStackCoverage(null)
    setStackLookup((previous) =>
      previous.names.length === 0 ? previous : { names: [], id: previous.id + 1 }
    )
  }

  async function handleSearch(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault()
    const trimmed = query.trim()
    if (!trimmed) {
      searchRequest.current += 1
      setSearchResults([])
      setSearchStatus('idle')
      setSearchError('Enter a compound name to search.')
      setSearchLookup((previous) => ({ name: '', id: previous.id + 1 }))
      return
    }

    // Only the newest search may write its results; an older, slower reply is dropped.
    const request = ++searchRequest.current
    setSearchStatus('loading')
    setSearchError(null)
    setSearchLookup((previous) => ({ name: trimmed, id: previous.id + 1 }))
    try {
      const results = await searchCompounds(trimmed)
      if (request !== searchRequest.current) return
      setSearchResults(results)
      setSearchStatus('success')
      if (results.length === 0) {
        setSearchError('No compounds matched your search.')
      }
    } catch (error) {
      if (request !== searchRequest.current) return
      setSearchStatus('error')
      setSearchResults([])
      setSearchError(error instanceof Error ? error.message : 'Search failed')
    }
  }

  async function handleDocumentSearch(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault()
    const trimmed = docQuery.trim()
    if (!trimmed) {
      setDocResults([])
      setDocMeta(null)
      setDocStatus('idle')
      setDocError('Enter a research question to search the knowledge base.')
      return
    }

    setDocStatus('loading')
    setDocError(null)
    setDocMeta(null)
    try {
      const payload = await searchDocuments(trimmed)
      setDocResults(payload.results)
      setDocMeta(payload.meta ?? null)
      setDocStatus('success')
      if (!payload.results || payload.results.length === 0) {
        setDocError('No supporting passages found for that question.')
      }
    } catch (error) {
      setDocStatus('error')
      setDocResults([])
      setDocMeta(null)
      setDocError(error instanceof Error ? error.message : 'Document search failed')
    }
  }

  async function handlePairSubmit(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault()
    const a = pairA.trim()
    const b = pairB.trim()

    if (!a || !b) {
      clearPairResults()
      setPairStatus('error')
      setPairError('Enter two compounds to run a pair check.')
      return
    }

    const request = ++pairRequest.current
    setPairStatus('loading')
    setPairError(null)
    // Label statements are looked up separately, so they still show when the names are not
    // in the assessed compound list.
    setPairLookup((previous) => ({ names: [a, b], id: previous.id + 1 }))
    try {
      const data = await fetchInteraction(a, b)
      if (request !== pairRequest.current) return
      setPairData(data)
      setPairStatus('success')
    } catch (error) {
      if (request !== pairRequest.current) return
      setPairData(null)
      setPairStatus('error')
      setPairError(explainLookupError(error instanceof Error ? error.message : 'Interaction lookup failed'))
    }
  }

  async function handleStackSubmit(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault()
    const compounds = parseStackInput(stackText)
    if (compounds.length < 2) {
      clearStackResults()
      setStackStatus('error')
      setStackError('List at least two compounds to evaluate the stack.')
      return
    }

    const request = ++stackRequest.current
    setStackStatus('loading')
    setStackError(null)
    setStackLookup((previous) => ({ names: compounds, id: previous.id + 1 }))
    try {
      const data = await checkStack(compounds)
      if (request !== stackRequest.current) return
      const parsed = parseStackData(data, compounds)

      setStackInteractions(parsed.interactions)
      setStackCompounds(parsed.compounds)
      setStackCoverage(data.coverage ?? null)
      setStackStatus('success')
      setStackError([
        data.unrecognised?.length ? `Not recognised, so not checked: ${data.unrecognised.join(', ')}` : '',
        data.duplicates_removed?.length ? `Duplicates removed: ${data.duplicates_removed.join(', ')}` : '',
      ].filter(Boolean).join('. ') || null)
    } catch (error) {
      if (request !== stackRequest.current) return
      setStackInteractions(null)
      setStackCompounds([])
      setStackCoverage(null)
      setStackStatus('error')
      setStackError(explainLookupError(error instanceof Error ? error.message : 'Stack check failed'))
    }
  }

  const pair = pairData?.interaction
  const resolvedPairSources = resolveSources(pairData)
  const riskScore = pairData?.risk_score
  const formattedRiskScore = typeof riskScore === 'number' ? riskScore.toFixed(2) : 'N/A'

  const pairHeading = pair
    ? `${pair.a || 'Compound A'} × ${pair.b || 'Compound B'}`
    : 'Selected pair'

  return (
    <div className="app-shell">
      <header className="app-header">
        <h1>Supplement Interaction Tracker</h1>
        <p className="app-tagline">
          Search compounds, read FDA label statements, and check pairs and stacks against assessed records.
        </p>
        <p className="app-notice" role="note">
          This site quotes FDA drug-label text. It is not medical advice, and nothing here has been
          assessed by SuppTracker. A missing result does not mean a combination is safe. Ask a
          pharmacist or doctor before combining medicines and supplements.
        </p>
      </header>

      <main className="grid">
        <section className="card accent-card full-width">
          <div className="card-header">
            <h2>Dataset overview</h2>
            <p>Instant snapshot of every resource loaded by the API powering this deployment.</p>
          </div>
          {overviewStatus === 'loading' && <p className="status">Loading dataset statistics…</p>}
          {overviewStatus === 'error' && <p className="status status-error">{overviewError}</p>}
          {overviewStatus === 'success' && health && (
            <>
              <ul className="stat-grid" aria-live="polite">
                <li className="stat">
                  <span className="stat-label">Compounds available</span>
                  <strong className="stat-value">{health.compounds_loaded}</strong>
                  <span className="stat-footnote">Ready for search & stack analysis</span>
                </li>
                <li className="stat">
                  <span className="stat-label">Assessed interaction records</span>
                  <strong className="stat-value">{health.interactions_loaded}</strong>
                  <span className="stat-footnote">
                    {health.interactions_loaded > 0
                      ? 'Each with evidence and risk scores'
                      : 'None loaded: pair and stack checks can only report "not assessed"'}
                  </span>
                </li>
                <li className="stat">
                  <span className="stat-label">Evidence sources</span>
                  <strong className="stat-value">{health.sources_loaded}</strong>
                  <span className="stat-footnote">
                    {health.interactions_loaded > 0
                      ? 'Citations powering recommendations'
                      : 'Loaded, but not yet cited by any assessed record'}
                  </span>
                </li>
              </ul>

              {health.status === 'degraded' && health.issues && health.issues.length > 0 && (
                <div className="health-alert" role="status" aria-live="assertive">
                  <strong className="health-alert-title">Dataset loaded with warnings</strong>
                  <ul>
                    {health.issues.map((issue) => (
                      <li key={`${issue.source}:${issue.code ?? issue.error}`.slice(0, 120)}>
                        <span className="health-issue-source">{issue.source}:</span>{' '}
                        <span className="health-issue-message">
                          {issue.error ??
                            `${(issue.code ?? 'unknown_problem').replace(/_/g, ' ')}${
                              issue.count != null ? ` (${issue.count})` : ''
                            }`}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {topInteractions.length > 0 && (
                <div className="overview-panels">
                  <div className="overview-panel">
                    <h3>Most notable interactions</h3>
                    <ol className="interaction-list">
                      {topInteractions.map((interaction) => (
                        <li key={interaction.id}>
                          <div className="interaction-heading">
                            <span className="interaction-pair">{datasetCompoundLookup[interaction.a]?.name ?? interaction.a}</span>
                            <span className="interaction-divider">×</span>
                            <span className="interaction-pair">{datasetCompoundLookup[interaction.b]?.name ?? interaction.b}</span>
                          </div>
                          <div className="interaction-meta">
                            <span className={severityClass(interaction.severity)}>Severity: {interaction.severity}</span>
                            <span className="badge badge-evidence">Evidence: {interaction.evidence}</span>
                            <span className="badge badge-muted">Risk: {interaction.risk_score.toFixed(2)}</span>
                          </div>
                          <p className="interaction-effect">{interaction.effect ?? 'No description available.'}</p>
                        </li>
                      ))}
                    </ol>
                  </div>
                  <div className="overview-panel">
                    <h3>Compound quick reference</h3>
                    <ul className="compound-list">
                      {allCompounds.map((compound) => {
                        const externalLinks = compoundExternalLinks(compound)
                        const synonyms = normaliseSynonyms(compound)
                        return (
                          <li key={compound.id}>
                            <div className="compound-name-row">
                              <span className="compound-name">{compound.name}</span>
                              {compound.class && <span className="badge badge-muted">{compound.class}</span>}
                            </div>
                            <dl>
                              <div>
                                <dt>Dose guide</dt>
                                <dd>{formatDose(compound)}</dd>
                              </div>
                              <div>
                                <dt>Route</dt>
                                <dd>{compound.route ?? 'Not specified'}</dd>
                              </div>
                              {synonyms.length > 0 && (
                                <div>
                                  <dt>Also known as</dt>
                                  <dd>{synonyms.join(', ')}</dd>
                                </div>
                              )}
                              {externalLinks.length > 0 && (
                                <div>
                                  <dt>External links</dt>
                                  <dd>
                                    <ul className="link-list">
                                      {externalLinks.map((link) => (
                                        <li key={link.key}>
                                          <a href={link.href} target="_blank" rel="noreferrer">
                                            {link.label}
                                          </a>
                                        </li>
                                      ))}
                                    </ul>
                                  </dd>
                                </div>
                              )}
                            </dl>
                          </li>
                        )
                      })}
                    </ul>
                  </div>
                </div>
              )}
            </>
          )}
        </section>

        <section className="card">
          <div className="card-header">
            <h2>Search compounds</h2>
            <p>Find a compound in the dataset, or a name used in the FDA label statements.</p>
          </div>
          <form onSubmit={handleSearch} className="stacked">
            <label className="sr-only" htmlFor="search-input">
              Compound search query
            </label>
            <div className="input-row">
              <input
                id="search-input"
                value={query}
                onChange={(event) => {
                  setQuery(event.target.value)
                  // The label-statement note below describes the name that was searched, not
                  // the one now being typed.
                  setSearchLookup((previous) =>
                    previous.name === '' ? previous : { name: '', id: previous.id + 1 }
                  )
                }}
                placeholder="e.g. melatonin or warfarin"
                autoComplete="off"
                spellCheck={false}
              />
              <button type="submit" className="primary">Search</button>
            </div>
          </form>
          {searchStatus === 'loading' && <p className="status">Searching…</p>}
          {searchError && (
            <p className={`status ${searchStatus === 'error' ? 'status-error' : 'status-info'}`}>
              {searchError}
            </p>
          )}
          {hasSearchResults && (
            <ul className="pill-grid" aria-live="polite">
              {searchResults.map((compound) => {
                const externalLinks = compoundExternalLinks(compound)
                const synonyms = normaliseSynonyms(compound)
                return (
                  <li key={compound.id} className="pill">
                    <span className="pill-name">{compound.name}</span>
                    {synonyms.length > 0 && (
                      <span className="pill-meta">Also known as {synonyms.join(', ')}</span>
                    )}
                    {externalLinks.length > 0 && (
                      <ul className="link-list">
                        {externalLinks.map((link) => (
                          <li key={link.key}>
                            <a href={link.href} target="_blank" rel="noreferrer">
                              {link.label}
                            </a>
                          </li>
                        ))}
                      </ul>
                    )}
                  </li>
                )
              })}
            </ul>
          )}
          <LabelStatementNameHits
            name={searchLookup.name}
            requestId={searchLookup.id}
            compoundMatches={searchStatus === 'success' ? searchResults.length : null}
            onShow={(filter) =>
              setLabelRequest((previous) => ({ ...filter, token: (previous?.token ?? 0) + 1 }))
            }
          />
        </section>

        {/* Developer notes are not shipped in the public image, so the search only appears
            where there is something to search. */}
        {(health?.docs_indexed ?? 0) > 0 && (
        <section className="card">
          <div className="card-header">
            <h2>Project notes search</h2>
            <p>Keyword search across this project's own documentation. These are developer notes, not clinical evidence.</p>
          </div>
          <form onSubmit={handleDocumentSearch} className="stacked">
            <label className="sr-only" htmlFor="doc-search-input">
              Document search query
            </label>
            <div className="input-row">
              <input
                id="doc-search-input"
                value={docQuery}
                onChange={(event) => setDocQuery(event.target.value)}
                placeholder="e.g. label statements licence"
                autoComplete="off"
              />
              <button type="submit" className="primary">
                Search notes
              </button>
            </div>
          </form>
          {docStatus === 'loading' && <p className="status">Searching documents…</p>}
          {docError && (
            <p className={`status ${docStatus === 'error' ? 'status-error' : 'status-info'}`}>
              {docError}
            </p>
          )}
          {docMeta && (
            <p className="status status-info doc-meta">
              {docMeta.uses_embeddings
                ? `Gemini embeddings${docMeta.embedding_model ? ` (${docMeta.embedding_model})` : ''} active`
                : 'Keyword search'}
              {docMeta.documents_indexed > 0 && ` • ${docMeta.documents_indexed} passages indexed`}
            </p>
          )}
          {hasDocResults && (
            <ul className="doc-list" aria-live="polite">
              {docResults.map((result) => (
                <li key={result.id} className="doc-result">
                  <div className="doc-result-header">
                    <span className="doc-title">{result.title}</span>
                    <span className="doc-score">Score: {formatDocumentScore(result.score)}</span>
                  </div>
                  <p className="doc-snippet">{result.snippet}</p>
                  <p className="doc-source">Source: {result.source ?? 'Knowledge base'}</p>
                </li>
              ))}
            </ul>
          )}
        </section>
        )}

        <LabelStatements request={labelRequest} />

        <section className="card">
          <div className="card-header">
            <h2>Pair checker</h2>
            <p>Look up two names: any assessed record, plus FDA label statements that name them together.</p>
          </div>
          <form onSubmit={handlePairSubmit} className="stacked">
            <div className="pair-inputs">
              <label className="sr-only" htmlFor="pair-a">Compound A</label>
              <input
                id="pair-a"
                value={pairA}
                onChange={(event) => {
                  setPairA(event.target.value)
                  clearPairResults()
                }}
                placeholder="First compound"
                autoComplete="off"
                spellCheck={false}
              />
              <span className="pair-separator" aria-hidden="true">
                and
              </span>
              <label className="sr-only" htmlFor="pair-b">Compound B</label>
              <input
                id="pair-b"
                value={pairB}
                onChange={(event) => {
                  setPairB(event.target.value)
                  clearPairResults()
                }}
                placeholder="Second compound"
                autoComplete="off"
                spellCheck={false}
              />
              <button type="submit" className="primary">
                Check pair
              </button>
            </div>
          </form>
          {pairStatus === 'loading' && <p className="status">Checking interaction…</p>}
          {pairError && (
            <p className={`status ${/not recognised|not found/i.test(pairError) ? 'status-info' : 'status-error'}`}>
              {pairError}
            </p>
          )}
          {pairData?.assessment === 'not_assessed' && (
            <p className="status status-info" role="status">
              {pairData.message ?? 'No assessed interaction record is available for this pair. This does not mean the combination is safe.'}
            </p>
          )}
          {pair && pairStatus === 'success' && (
            <div className="pair-result" aria-live="polite">
              <h3>{pairHeading}</h3>
              <div className="badges">
                <span className={severityClass(pair.severity)}>Severity: {pair.severity}</span>
                <span className="badge badge-evidence">Evidence: {pair.evidence}</span>
                <span className="badge badge-muted">Risk score: {formattedRiskScore}</span>
              </div>
              <dl className="description">
                <div>
                  <dt>Effect</dt>
                  <dd>{pair.effect}</dd>
                </div>
                <div>
                  <dt>Recommended action</dt>
                  <dd>{pair.action}</dd>
                </div>
              </dl>
              <details className="sources">
                <summary>Evidence sources ({resolvedPairSources.length})</summary>
                <ul>
                  {resolvedPairSources.length === 0 && <li>No citations provided.</li>}
                  {resolvedPairSources.map((source, index) => (
                    <li key={source.id ?? index}>{sourceLabel(source, index)}</li>
                  ))}
                </ul>
              </details>
            </div>
          )}
          <LabelStatementMatches names={pairLookup.names} requestId={pairLookup.id} />
        </section>

        <section className="card">
          <div className="card-header">
            <h2>Stack checker</h2>
            <p>Paste a list separated by commas, semicolons or new lines.</p>
          </div>
          <form onSubmit={handleStackSubmit} className="stacked">
            <label className="sr-only" htmlFor="stack-input">
              Supplement stack list
            </label>
            <textarea
              id="stack-input"
              rows={4}
              value={stackText}
              onChange={(event) => {
                setStackText(event.target.value)
                clearStackResults()
              }}
              placeholder={DEFAULT_STACK_EXAMPLE}
              spellCheck={false}
            />
            <div className="actions">
              <button type="submit" className="primary">
                Check stack
              </button>
              <button
                type="button"
                onClick={() => {
                  setStackText(DEFAULT_STACK_EXAMPLE)
                  clearStackResults()
                }}
                className="ghost"
              >
                Use example
              </button>
            </div>
          </form>
          {stackStatus === 'loading' && <p className="status">Evaluating stack…</p>}
          {stackError && (
            <p className={`status ${stackStatus === 'error' ? 'status-error' : 'status-info'}`}>
              {stackError}
            </p>
          )}
          {shouldShowStackResults && (
            <div className="stack-results" aria-live="polite">
              <h3>
                {stackHasInteractions
                  ? `Interactions found for ${stackCompoundLabels.join(', ')}`
                  : stackCompoundLabels.length > 0
                    ? `No assessed interactions were found in ${stackCompoundLabels.join(', ')}. This does not mean the combination is safe.`
                    : 'No assessed interactions were found in this stack. This does not mean the combination is safe.'
                }
              </h3>
              {stackCoverage && stackCoverage.not_assessed_pairs > 0 && (
                <p className="status status-info">
                  {stackCoverage.assessed_pairs} of {stackCoverage.total_pairs} pairs have assessed records. {stackCoverage.not_assessed_pairs} {stackCoverage.not_assessed_pairs === 1 ? 'pair remains' : 'pairs remain'} unassessed; absence of a record does not mean safe.
                </p>
              )}
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
                        <td>{datasetCompoundLookup[interaction.a]?.name ?? compoundLookup[interaction.a]?.name ?? interaction.a}</td>
                        <td>{datasetCompoundLookup[interaction.b]?.name ?? compoundLookup[interaction.b]?.name ?? interaction.b}</td>
                        <td>
                          <span className={severityClass(interaction.severity)}>{interaction.severity}</span>
                        </td>
                        <td>{interaction.evidence}</td>
                        <td
                          title={
                            interaction.action_resolved ??
                            interaction.action ??
                            undefined
                          }
                        >
                          {interaction.risk_score.toFixed(2)}
                          {interaction.bucket && ` (${interaction.bucket})`}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}
          <LabelStatementMatches names={stackLookup.names} requestId={stackLookup.id} />
        </section>
      </main>
    </div>
  )
}
