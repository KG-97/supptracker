import React, { useState } from 'react'
import { search, getInteraction, checkStack } from './api'

export default function App() {
  const [q, setQ] = useState('')
  const [results, setResults] = useState<any[]>([])
  const [pairA, setPairA] = useState('')
  const [pairB, setPairB] = useState('')
  const [pairData, setPairData] = useState<any | null>(null)
  const [stackText, setStackText] = useState('creatine, caffeine, magnesium')
  const [stack, setStack] = useState<any[] | null>(null)

  const doSearch = async () => {
    const data = await search(q)
    setResults(data.results || data.compounds || [])
  }

  const openPair = async () => {
    const a = pairA.trim()
    const b = pairB.trim()
    if (!a || !b) {
      setPairData(null)
      return
    }
    const data = await getInteraction(a, b)
    setPairData(data)
  }

  const doStack = async () => {
    const items = stackText.split(',').map(s => s.trim()).filter(Boolean)
    const data = await checkStack(items)
    setStack(data.interactions || data.cells || [])
  }

  return (
    <div style={{ fontFamily: 'Inter, system-ui, sans-serif', margin: '24px', maxWidth: 960 }}>
      <h1>Supplement Interaction Tracker</h1>

      <section style={{ marginTop: 16, padding: 16, border: '1px solid #ccc', borderRadius: 12 }}>
        <h2>Search</h2>
        <input value={q} onChange={e => setQ(e.target.value)} placeholder='search compound' style={{ padding: 8, width: '70%' }} />
        <button onClick={doSearch} style={{ marginLeft: 8, padding: '8px 12px' }}>Search</button>
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
        {pairData && (
          <div style={{ marginTop: 12, padding: 12, border: '1px solid #eee', borderRadius: 12 }}>
            <h3>{pairData.interaction.a} × {pairData.interaction.b}</h3>
            <p><b>Severity:</b> {pairData.interaction.severity} | <b>Evidence:</b> {pairData.interaction.evidence}</p>
            <p><b>Risk score:</b> {pairData.risk_score}</p>
            <p><b>Effect:</b> {pairData.interaction.effect}</p>
            <p><b>Action:</b> {pairData.interaction.action}</p>
            <details><summary>Sources</summary><ul>
              {(pairData.sources || []).map((s: any) => (<li key={s.id}>{s.citation || s.id}</li>))}
            </ul></details>
          </div>
        )}
      </section>

      <section style={{ marginTop: 16, padding: 16, border: '1px solid #ccc', borderRadius: 12 }}>
        <h2>Stack Checker</h2>
        <textarea value={stackText} onChange={e => setStackText(e.target.value)} rows={3} style={{ width: '100%', padding: 8 }} />
        <div style={{ marginTop: 8 }}><button onClick={doStack}>Check Stack</button></div>
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
