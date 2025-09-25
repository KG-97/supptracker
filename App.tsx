import React, { useState } from 'react'
import { search, getInteraction, checkStack } from './api'

// Helper function to resolve sources from API response
function resolveSources(pairData: any): any[] {
  // Prefer detailed source objects over raw IDs
  const detailedSources = pairData.sources || []
  const interactionSources = pairData.interaction?.sources || []
  
  // Check if interaction.sources contains objects with citation info
  if (interactionSources.length > 0 && typeof interactionSources[0] === 'object' && interactionSources[0].citation) {
    return interactionSources
  }
  
  // Otherwise fall back to the detailed sources array
  return detailedSources
}

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

  return (
    <div style={{ fontFamily: 'system-ui, sans-serif', margin: 'auto', maxWidth: 800, padding: 20 }}>
      <h1>Supplement Interaction Tracker</h1>
      
      <section style={{ marginTop: 20, padding: 12, border: '1px solid #ccc', borderRadius: 8 }}>
        <h2>Search</h2>
        <input
          value={q}
          onChange={e => setQ(e.target.value)}
          placeholder='search compound'
          style={{ padding: 8, width: '70%' }}
        />
        <button onClick={doSearch} style={{ marginLeft: 8, padding: 8 }}>Search</button>
        {searchError && (
          <div style={{ color: 'red', marginTop: 8 }}>{searchError}</div>
        )}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 12 }}>
          {results.map(r => <span key={r.id} style={{ padding: '4px 8px', border: '1px solid #ddd', borderRadius: 4 }}>{r.name}</span>)}
        </div>
      </section>
      
      <section style={{ marginTop: 20, padding: 12, border: '1px solid #ccc', borderRadius: 8 }}>
        <h2>Pair Checker</h2>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <input
            value={pairA}
            onChange={e => setPairA(e.target.value)}
            placeholder='compound A'
            style={{ padding: 8 }}
          />
          ×
          <input
            value={pairB}
            onChange={e => setPairB(e.target.value)}
            placeholder='compound B'
            style={{ padding: 8 }}
          />
          <button disabled={!pairA.trim() || !pairB.trim()} onClick={openPair}>Check</button>
        </div>
        {pairError && (
          <div style={{ color: 'red', marginTop: 8 }}>{pairError}</div>
        )}
        {pairData && (
          <div style={{ marginTop: 12, padding: 12, border: '1px solid #eee', borderRadius: 12 }}>
            <h3>
              {(pairData.pair?.a ?? pairData.interaction?.compound_a ?? pairData.interaction?.a ?? '—')}
              {' × '}
              {(pairData.pair?.b ?? pairData.interaction?.compound_b ?? pairData.interaction?.b ?? '—')}
            </h3>
            <p>
              <b>Severity:</b> {pairData.interaction?.severity}
              {' | '}
              <b>Evidence:</b> {pairData.interaction?.evidence_grade ?? pairData.interaction?.evidence}
            </p>
            <p><b>Risk score:</b> {pairData.interaction?.score ?? pairData.risk_score}</p>
            <p><b>Effect:</b> {pairData.interaction?.effect}</p>
            <p><b>Action:</b> {pairData.interaction?.action}</p>
            <details><summary>Sources</summary><ul>
              {resolveSources(pairData).map((s: any, idx: number) => (
                <li key={s.id || idx}>{s.citation || s.id || s}</li>
              ))}
            </ul></details>
          </div>
        )}
      </section>
      
      <section style={{ marginTop: 20, padding: 12, border: '1px solid #ccc', borderRadius: 8 }}>
        <h2>Stack Checker</h2>
        <textarea
          value={stackText}
          onChange={e => setStackText(e.target.value)}
          rows={3}
          style={{ width: '100%', padding: 8 }}
        />
        <div style={{ marginTop: 8 }}><button onClick={doStack}>Check Stack</button></div>
        {stackError && (
          <div style={{ color: 'red', marginTop: 8 }}>{stackError}</div>
        )}
        {stack && stack.length > 0 && (
          <div style={{ marginTop: 12 }}>
            <table style={{ borderCollapse: 'collapse', width: '100%' }}>
              <thead>
                <tr>
                  <th style={{ border: '1px solid #ccc', padding: 8 }}>A</th>
                  <th style={{ border: '1px solid #ccc', padding: 8 }}>B</th>
                  <th style={{ border: '1px solid #ccc', padding: 8 }}>Severity</th>
                  <th style={{ border: '1px solid #ccc', padding: 8 }}>Evidence</th>
                  <th style={{ border: '1px solid #ccc', padding: 8 }}>Risk</th>
                </tr>
              </thead>
              <tbody>
                {stack.map((inter: any, i: number) => (
                  <tr key={i}>
                    <td style={{ border: '1px solid #ccc', padding: 8 }}>{inter.a}</td>
                    <td style={{ border: '1px solid #ccc', padding: 8 }}>{inter.b}</td>
                    <td style={{ border: '1px solid #ccc', padding: 8 }}>{inter.severity}</td>
                    <td style={{ border: '1px solid #ccc', padding: 8 }}>{inter.evidence}</td>
                    <td style={{ border: '1px solid #ccc', padding: 8, textAlign: 'right' }}>{inter.risk_score.toFixed(2)}</td>
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
