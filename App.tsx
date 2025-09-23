import React, { useState } from 'react'
import { search, getInteraction, checkStack } from './api'

export default function App() {
  const [q, setQ] = useState('')
  const [results, setResults] = useState<any[]>([])
  const [searchError, setSearchError] = useState<string | null>(null)
  const [pairA, setPairA] = useState('')
  const [pairB, setPairB] = useState('')
  const [pairData, setPairData] = useState<any | null>(null)
  const [pairError, setPairError] = useState<string | null>(null)
  const [stackText, setStackText] = useState('creatine, caffeine, magnesium')
  const [stack, setStack] = useState<any[] | null>(null)
  const [stackError, setStackError] = useState<string | null>(null)

  const doSearch = async () => {
    try {
      setSearchError(null)
      const data = await search(q)
      setResults(data.results || data.compounds || [])
    } catch (err) {
      setResults([])
      setSearchError(err instanceof Error ? err.message : 'Search failed')
    }
  }

  const openPair = async () => {
    const a = pairA.trim()
    const b = pairB.trim()
    if (!a || !b) {
      setPairData(null)
      setPairError('Enter two compounds to check for an interaction.')
      return
    }
    try {
      setPairError(null)
      const data = await getInteraction(a, b)
      setPairData(data)
    } catch (err) {
      setPairData(null)
      setPairError(err instanceof Error ? err.message : 'Interaction lookup failed')
    }
  }

  const doStack = async () => {
    const items = stackText.split(',').map(s => s.trim()).filter(Boolean)
    if (items.length === 0) {
      setStack(null)
      setStackError('Enter at least one compound to check the stack.')
      return
    }
    try {
      setStackError(null)
      const data = await checkStack(items)
      setStack(data.interactions || data.cells || [])
    } catch (err) {
      setStack(null)
      setStackError(err instanceof Error ? err.message : 'Stack check failed')
    }
  }

  const pair = pairData?.pair || {}
  const interaction = pairData?.interaction || {}
  const compoundA = pair?.a ?? interaction?.compound_a ?? interaction?.a ?? ''
  const compoundB = pair?.b ?? interaction?.compound_b ?? interaction?.b ?? ''
  const evidence = interaction?.evidence_grade ?? interaction?.evidence ?? 'Unknown'
  const severity = interaction?.severity ?? 'Unknown'
  const effect = interaction?.effect ?? 'Not specified'
  const action = interaction?.action_resolved ?? interaction?.action ?? 'No specific action'
  const rawRiskScore = interaction?.score ?? pairData?.risk_score
  const riskScore =
    typeof rawRiskScore === 'number'
      ? rawRiskScore
      : typeof rawRiskScore === 'string'
        ? Number.parseFloat(rawRiskScore)
        : undefined
  const formattedRiskScore =
    riskScore !== undefined && !Number.isNaN(riskScore)
      ? riskScore.toFixed(2)
      : rawRiskScore ?? 'N/A'
  const sources = (interaction?.sources ?? pairData?.sources ?? []) as any[]

  return (
    <div style={{ fontFamily: 'Inter, system-ui, sans-serif', margin: '24px', maxWidth: 960 }}>
      <h1>Supplement Interaction Tracker</h1>

      <section style={{ marginTop: 16, padding: 16, border: '1px solid #ccc', borderRadius: 12 }}>
        <h2>Search</h2>
        <input value={q} onChange={e => setQ(e.target.value)} placeholder='search compound' style={{ padding: 8, width: '70%' }} />
        <button onClick={doSearch} style={{ marginLeft: 8, padding: '8px 12px' }}>Search</button>
        {searchError && (
          <div style={{ marginTop: 8, color: 'crimson' }}>{searchError}</div>
        )}
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 12 }}>
          {results.map(r => (<span key={r.id} style={{ padding: '6px 10px', border: '1px solid #ddd', borderRadius: 16 }}>{r.name}</span>))}
        </div>
      </section>

      <section style={{ marginTop: 16, padding: 16, border: '1px solid #ccc', borderRadius: 12 }}>
        <h2>Pair Checker</h2>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <input
            value={pairA}
            onChange={e => setPairA(e.target.value)}
            placeholder='compound A'
            style={{ padding: 8 }}
          />
          <span>×</span>
          <input
            value={pairB}
            onChange={e => setPairB(e.target.value)}
            placeholder='compound B'
            style={{ padding: 8 }}
          />
          <button onClick={openPair} disabled={!pairA.trim() || !pairB.trim()}>Check</button>
        </div>
        {pairError && (
          <div style={{ marginTop: 8, color: 'crimson' }}>{pairError}</div>
        )}
        {pairData && (
          <div style={{ marginTop: 12, padding: 12, border: '1px solid #eee', borderRadius: 12 }}>
            <h3>{compoundA || 'Compound A'} × {compoundB || 'Compound B'}</h3>
            <p><b>Severity:</b> {severity} | <b>Evidence:</b> {evidence}</p>
            <p><b>Risk score:</b> {formattedRiskScore}</p>
            <p><b>Effect:</b> {effect}</p>
            <p><b>Action:</b> {action}</p>
            <details>
              <summary>Sources</summary>
              <ul>
                {sources.length === 0 && <li>No cited sources</li>}
                {sources.map((s: any, idx: number) => {
                  if (!s) return null
                  if (typeof s === 'string') {
                    return <li key={s}>{s}</li>
                  }
                  const label = s.citation || s.title || s.reference || s.id || `Source ${idx + 1}`
                  const key = s.id || `${label}-${idx}`
                  return <li key={key}>{label}</li>
                })}
              </ul>
            </details>
          </div>
        )}
      </section>

      <section style={{ marginTop: 16, padding: 16, border: '1px solid #ccc', borderRadius: 12 }}>
        <h2>Stack Checker</h2>
        <textarea value={stackText} onChange={e => setStackText(e.target.value)} rows={3} style={{ width: '100%', padding: 8 }} />
        <div style={{ marginTop: 8 }}><button onClick={doStack}>Check Stack</button></div>
        {stackError && (
          <div style={{ marginTop: 8, color: 'crimson' }}>{stackError}</div>
        )}
        {stack && stack.length > 0 && (
          <div style={{ marginTop: 12 }}>
            <table style={{ borderCollapse: 'collapse' }}>
              <thead>
                <tr>
                  <th style={{ border: '1px solid #ddd', padding: '4px 8px' }}>A</th>
                  <th style={{ border: '1px solid #ddd', padding: '4px 8px' }}>B</th>
                  <th style={{ border: '1px solid #ddd', padding: '4px 8px' }}>Severity</th>
                  <th style={{ border: '1px solid #ddd', padding: '4px 8px' }}>Evidence</th>
                  <th style={{ border: '1px solid #ddd', padding: '4px 8px' }}>Risk</th>
                </tr>
              </thead>
              <tbody>
                {stack.map((inter: any, i: number) => (
                  <tr key={i}>
                    <td style={{ border: '1px solid #ddd', padding: '4px 8px' }}>{inter.a}</td>
                    <td style={{ border: '1px solid #ddd', padding: '4px 8px' }}>{inter.b}</td>
                    <td style={{ border: '1px solid #ddd', padding: '4px 8px' }}>{inter.severity}</td>
                    <td style={{ border: '1px solid #ddd', padding: '4px 8px' }}>{inter.evidence}</td>
                    <td style={{ border: '1px solid #ddd', padding: '4px 8px', textAlign: 'center' }}>{inter.risk_score.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
