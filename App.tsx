import React, { useState, useEffect, useRef } from 'react'
import { search, getCompounds, getInteraction, checkStack } from './api'

// ── Types ─────────────────────────────────────────────────────────────────────
interface CompoundHit { id: string; name: string; synonyms: string[] }
interface CompoundDetail extends CompoundHit {
  compound_class: string; route: string; common_dose: string; qt_risk: string; notes: string
}
interface InteractionSource { id: string; title?: string; citation?: string; identifier?: string; date?: string }
interface InteractionDetail {
  compound_a: string; compound_b: string; severity?: string; evidence_grade?: string;
  mechanism_tags?: string; effect_summary?: string; score: number; bucket: string;
  action_resolved: string; sources: InteractionSource[]
}
interface InteractionResponse { pair: { a: string; b: string }; interaction: InteractionDetail }
interface StackCell { a: string; b: string; score: number; bucket: string; action: string; effect_summary?: string }
interface StackResponse { items: string[]; matrix: (number | null)[][]; cells: StackCell[] }

// ── Helpers ───────────────────────────────────────────────────────────────────
function severityBadgeClass(s?: string): string {
  const k = (s || '').toLowerCase()
  if (k === 'none' || k === 'low') return 'badge badge-none'
  if (k === 'mild') return 'badge badge-mild'
  if (k === 'moderate' || k === 'medium') return 'badge badge-moderate'
  if (k === 'high' || k === 'severe') return 'badge badge-high'
  if (k === 'critical') return 'badge badge-critical'
  return 'badge badge-none'
}

function bucketCellClass(b?: string | null): string {
  if (!b) return 'cell-empty'
  const k = b.toLowerCase()
  if (k === 'low' || k === 'none') return 'cell-low'
  if (k === 'mild') return 'cell-mild'
  if (k === 'medium' || k === 'moderate') return 'cell-medium'
  if (k === 'high' || k === 'severe') return 'cell-high'
  if (k === 'critical') return 'cell-critical'
  return 'cell-empty'
}

function scoreToColor(score: number): string {
  if (score <= 0.3) return '#22c55e'
  if (score <= 0.9) return '#eab308'
  if (score <= 1.8) return '#f97316'
  if (score <= 2.7) return '#ef4444'
  return '#9333ea'
}

function scoreBarPct(score: number): number {
  return Math.min(100, (score / 3.5) * 100)
}

function classEmoji(cls: string): string {
  const map: Record<string, string> = {
    amino_acid: '🧬', amino_acid_derivative: '🧬', stimulant: '⚡', mineral: '💎',
    fatty_acid: '🐟', fat_soluble_vitamin: '☀️', water_soluble_vitamin: '🍊',
    adaptogen: '🌿', hormone: '🌙', antioxidant: '🛡️', alkaloid: '🍃',
    mushroom: '🍄', neurotransmitter: '🧠', macronutrient: '💪', microbiome: '🦠', protein: '💪',
  }
  return map[cls] || '💊'
}

// ── Loading spinner ──────────────────────────────────────────────────────────
function Spinner() { return <span className="spinner" /> }

// ── Compound Card ────────────────────────────────────────────────────────────
function CompoundCard({ c }: { c: CompoundDetail }) {
  return (
    <div className="compound-card">
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10, marginBottom: 8 }}>
        <span style={{ fontSize: 26 }}>{classEmoji(c.compound_class)}</span>
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 700, fontSize: 14, color: 'var(--text-primary)' }}>{c.name}</div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2, textTransform: 'capitalize' }}>
            {c.compound_class.replace(/_/g, ' ')} · {c.route}
          </div>
        </div>
        {c.qt_risk && c.qt_risk.toLowerCase() !== 'nan' && c.qt_risk.trim() !== '' && (
          <span className="badge badge-mild" title="QT prolongation risk">⚠️ QT</span>
        )}
      </div>
      {c.common_dose && c.common_dose !== 'nan' && (
        <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4 }}>
          <span style={{ color: 'var(--text-muted)' }}>Dose: </span>{c.common_dose}
        </div>
      )}
      {c.notes && c.notes !== 'nan' && c.notes.trim() !== '' && (
        <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 6, lineHeight: 1.5 }}>{c.notes}</div>
      )}
      {c.synonyms.length > 0 && (
        <div style={{ marginTop: 8, display: 'flex', flexWrap: 'wrap', gap: 4 }}>
          {c.synonyms.slice(0, 3).map((s, i) => (
            <span key={i} style={{ fontSize: 10, padding: '2px 7px', borderRadius: 99, background: 'rgba(255,255,255,0.05)', color: 'var(--text-muted)', border: '1px solid var(--border)' }}>
              {s}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Interaction Result ───────────────────────────────────────────────────────
function InteractionResult({ data }: { data: InteractionResponse }) {
  const { pair, interaction: ix } = data
  const mechs = ix.mechanism_tags ? ix.mechanism_tags.split(';').map(m => m.trim()).filter(Boolean) : []
  return (
    <div className="interaction-result">
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12, flexWrap: 'wrap' }}>
        <span style={{ fontFamily: 'Space Grotesk, sans-serif', fontWeight: 700, fontSize: 17 }}>
          {pair.a} <span style={{ color: 'var(--text-muted)' }}>×</span> {pair.b}
        </span>
        <span className={severityBadgeClass(ix.severity)}>⬤ {ix.severity || 'None'}</span>
        <span className={severityBadgeClass(ix.bucket)} style={{ marginLeft: 'auto' }}>
          {ix.bucket}
        </span>
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Grade {ix.evidence_grade || '—'}</span>
      </div>

      {ix.effect_summary && (
        <p style={{ fontSize: 14, color: 'var(--text-secondary)', lineHeight: 1.6, marginBottom: 12 }}>
          {ix.effect_summary}
        </p>
      )}

      <div style={{ padding: '10px 14px', borderRadius: 'var(--r-md)', background: 'rgba(6,182,212,0.07)', border: '1px solid rgba(6,182,212,0.15)', marginBottom: 12 }}>
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Recommended action: </span>
        <span style={{ fontSize: 13, fontWeight: 600, color: '#67e8f9' }}>{ix.action_resolved}</span>
      </div>

      <div style={{ marginBottom: 12 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: 'var(--text-muted)', marginBottom: 4 }}>
          <span>Risk score</span>
          <span style={{ fontWeight: 600, color: scoreToColor(ix.score) }}>{ix.score.toFixed(2)}</span>
        </div>
        <div className="score-bar-wrap">
          <div className="score-bar" style={{ width: `${scoreBarPct(ix.score)}%`, background: scoreToColor(ix.score) }} />
        </div>
      </div>

      {mechs.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <div className="section-label" style={{ marginBottom: 6 }}>Mechanisms</div>
          {mechs.map((m, i) => <span key={i} className="mechip">{m.replace(/_/g, ' ')}</span>)}
        </div>
      )}

      {ix.sources.length > 0 && (
        <details style={{ marginTop: 8 }}>
          <summary style={{ cursor: 'pointer', fontSize: 13, color: 'var(--text-secondary)', fontWeight: 500 }}>
            📚 {ix.sources.length} source{ix.sources.length > 1 ? 's' : ''}
          </summary>
          <ul style={{ marginTop: 8, paddingLeft: 16, display: 'flex', flexDirection: 'column', gap: 6 }}>
            {ix.sources.map((s, i) => (
              <li key={i} style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                {s.citation || s.title}
                {s.identifier && <span style={{ color: 'var(--accent-2)', marginLeft: 6 }}>{s.identifier}</span>}
                {s.date && <span style={{ color: 'var(--text-muted)', marginLeft: 6 }}>({s.date})</span>}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  )
}

// ── Search Tab ────────────────────────────────────────────────────────────────
function SearchTab() {
  const [q, setQ] = useState('')
  const [results, setResults] = useState<CompoundHit[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const doSearch = async () => {
    if (!q.trim()) return
    setLoading(true); setError('')
    try { const d = await search(q); setResults(d.compounds || []) }
    catch (e: any) { setError(e.message) }
    finally { setLoading(false) }
  }

  return (
    <div>
      <div style={{ display: 'flex', gap: 10 }}>
        <input ref={inputRef} className="input" value={q} onChange={e => setQ(e.target.value)}
          placeholder="Search by name, synonym or ID… e.g. magnesium"
          onKeyDown={e => e.key === 'Enter' && doSearch()} />
        <button id="search-btn" className="btn btn-primary" onClick={doSearch} disabled={loading}>
          {loading ? <Spinner /> : '🔍 Search'}
        </button>
      </div>
      {error && <div className="error-box" style={{ marginTop: 12 }}>{error}</div>}
      {results.length === 0 && !loading && q && !error && (
        <div className="empty-state">No compounds found for "<strong>{q}</strong>"</div>
      )}
      <div className="search-results">
        {results.map(r => (
          <div key={r.id} className="search-chip" title={r.synonyms.join(' · ')}>
            💊 {r.name}
            <span style={{ marginLeft: 6, fontSize: 11, color: 'var(--text-muted)' }}>({r.id})</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Pair Checker Tab ──────────────────────────────────────────────────────────
function PairTab() {
  const [a, setA] = useState('caffeine')
  const [b, setB] = useState('magnesium')
  const [result, setResult] = useState<InteractionResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const check = async () => {
    if (!a.trim() || !b.trim()) return
    setLoading(true); setError(''); setResult(null)
    try { setResult(await getInteraction(a.trim(), b.trim())) }
    catch (e: any) { setError(e.message) }
    finally { setLoading(false) }
  }

  return (
    <div>
      <div className="pair-row">
        <input id="pair-a" className="input" value={a} onChange={e => setA(e.target.value)}
          placeholder="Compound A — e.g. caffeine" onKeyDown={e => e.key === 'Enter' && check()} />
        <div className="pair-cross">×</div>
        <input id="pair-b" className="input" value={b} onChange={e => setB(e.target.value)}
          placeholder="Compound B — e.g. magnesium" onKeyDown={e => e.key === 'Enter' && check()} />
        <button id="pair-check-btn" className="btn btn-primary" onClick={check} disabled={loading}>
          {loading ? <Spinner /> : 'Check'}
        </button>
      </div>
      {error && <div className="error-box" style={{ marginTop: 12 }}>{error}</div>}
      {result && <InteractionResult data={result} />}
    </div>
  )
}

// ── Stack Analyzer Tab ────────────────────────────────────────────────────────
function StackTab() {
  const [stackText, setStackText] = useState('caffeine, magnesium, creatine, l_theanine, omega3, vitamin_d')
  const [stack, setStack] = useState<StackResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [hoveredCell, setHoveredCell] = useState<StackCell | null>(null)

  const compute = async () => {
    const items = stackText.split(',').map(s => s.trim()).filter(Boolean)
    if (items.length < 2) { setError('Enter at least 2 compounds'); return }
    setLoading(true); setError(''); setStack(null); setHoveredCell(null)
    try { setStack(await checkStack(items)) }
    catch (e: any) { setError(e.message) }
    finally { setLoading(false) }
  }

  const concerningCells = stack?.cells.filter(c => c.bucket !== 'Low' && c.bucket !== 'None') || []

  return (
    <div>
      <div className="section-label">Compound IDs, comma-separated</div>
      <textarea id="stack-input" className="input" value={stackText}
        onChange={e => setStackText(e.target.value)} rows={2}
        placeholder="e.g. caffeine, magnesium, creatine, l_theanine" />
      <div style={{ marginTop: 10 }}>
        <button id="stack-btn" className="btn btn-primary" onClick={compute} disabled={loading}>
          {loading ? <><Spinner /> Analysing…</> : '🧬 Compute Interaction Matrix'}
        </button>
      </div>
      {error && <div className="error-box" style={{ marginTop: 12 }}>{error}</div>}

      {stack && (
        <div style={{ marginTop: 20, animation: 'fadeSlideIn 0.35s ease' }}>
          {/* Heatmap */}
          <div className="section-label" style={{ marginBottom: 8 }}>Interaction Heatmap</div>
          <div style={{ overflowX: 'auto' }}>
            <table className="matrix-table">
              <thead>
                <tr>
                  <th style={{ textAlign: 'left', color: 'var(--text-muted)', fontSize: 11 }}></th>
                  {stack.items.map((it, i) => (
                    <th key={i}>{it}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {stack.items.map((row, i) => (
                  <tr key={i}>
                    <th style={{ textAlign: 'right', color: 'var(--text-secondary)', fontSize: 12, padding: '8px 12px', fontWeight: 600 }}>{row}</th>
                    {stack.matrix[i].map((cell, j) => {
                      if (i === j) return <td key={j} className="cell-self">—</td>
                      const matchCell = stack.cells.find(c =>
                        (c.a === stack.items[i] && c.b === stack.items[j]) ||
                        (c.b === stack.items[i] && c.a === stack.items[j])
                      )
                      if (cell === null) return (
                        <td key={j} className="cell-empty"
                          onMouseEnter={() => setHoveredCell(null)}>
                          —
                        </td>
                      )
                      return (
                        <td key={j} className={bucketCellClass(matchCell?.bucket)}
                          onMouseEnter={() => setHoveredCell(matchCell || null)}
                          onMouseLeave={() => setHoveredCell(null)}
                          title={matchCell?.effect_summary || ''}>
                          {cell.toFixed(2)}
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Hovered cell detail */}
          {hoveredCell && (
            <div style={{ marginTop: 12, padding: '10px 14px', borderRadius: 'var(--r-md)', background: 'rgba(124,58,237,0.08)', border: '1px solid rgba(124,58,237,0.2)', fontSize: 13, color: 'var(--text-secondary)', animation: 'fadeSlideIn 0.15s ease' }}>
              <strong style={{ color: 'var(--text-primary)' }}>{hoveredCell.a} × {hoveredCell.b}: </strong>
              {hoveredCell.effect_summary || hoveredCell.action}
            </div>
          )}

          {/* Alert list */}
          {concerningCells.length > 0 && (
            <div style={{ marginTop: 20 }}>
              <div className="section-label" style={{ marginBottom: 8 }}>⚠️ Interactions to watch</div>
              <div className="alert-list">
                {concerningCells
                  .sort((a, b) => b.score - a.score)
                  .map((c, i) => (
                    <div key={i} className="alert-item">
                      <span className={severityBadgeClass(c.bucket)} style={{ flexShrink: 0 }}>{c.bucket}</span>
                      <div>
                        <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 2 }}>{c.a} × {c.b}</div>
                        {c.effect_summary && <div style={{ color: 'var(--text-secondary)', fontSize: 12, lineHeight: 1.5 }}>{c.effect_summary}</div>}
                        <div style={{ marginTop: 4, fontSize: 12, color: '#67e8f9' }}>→ {c.action}</div>
                      </div>
                      <span style={{ marginLeft: 'auto', fontSize: 12, fontWeight: 700, color: scoreToColor(c.score), flexShrink: 0 }}>{c.score.toFixed(2)}</span>
                    </div>
                  ))}
              </div>
            </div>
          )}

          {concerningCells.length === 0 && (
            <div style={{ marginTop: 16, padding: '14px', borderRadius: 'var(--r-md)', background: 'rgba(34,197,94,0.07)', border: '1px solid rgba(34,197,94,0.2)', color: '#86efac', fontSize: 13, textAlign: 'center' }}>
              ✅ No significant interactions found in this stack
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Library Tab ───────────────────────────────────────────────────────────────
function LibraryTab() {
  const [compounds, setCompounds] = useState<CompoundDetail[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [filter, setFilter] = useState('')

  useEffect(() => {
    getCompounds()
      .then(d => setCompounds(d.compounds || []))
      .catch((e: any) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const visible = filter
    ? compounds.filter(c =>
        c.name.toLowerCase().includes(filter.toLowerCase()) ||
        c.id.toLowerCase().includes(filter.toLowerCase()) ||
        c.compound_class.toLowerCase().includes(filter.toLowerCase())
      )
    : compounds

  return (
    <div>
      <input id="library-filter" className="input" value={filter}
        onChange={e => setFilter(e.target.value)}
        placeholder="Filter by name, ID or class…" style={{ marginBottom: 16 }} />
      {loading && <div className="empty-state"><Spinner /> Loading library…</div>}
      {error && <div className="error-box">{error}</div>}
      {!loading && !error && (
        <>
          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 12 }}>{visible.length} compounds</div>
          <div className="compound-grid">
            {visible.map(c => <CompoundCard key={c.id} c={c} />)}
          </div>
        </>
      )}
    </div>
  )
}

// ── Legend ────────────────────────────────────────────────────────────────────
function Legend() {
  const items = [
    { cls: 'badge-none', label: 'None / Low' },
    { cls: 'badge-mild', label: 'Mild' },
    { cls: 'badge-moderate', label: 'Moderate' },
    { cls: 'badge-high', label: 'High / Severe' },
  ]
  return (
    <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center', marginTop: 8, marginBottom: 20 }}>
      <span style={{ fontSize: 11, color: 'var(--text-muted)', fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase' }}>Risk:</span>
      {items.map(it => (
        <span key={it.cls} className={`badge ${it.cls}`} style={{ fontSize: 11 }}>{it.label}</span>
      ))}
    </div>
  )
}

// ── App ───────────────────────────────────────────────────────────────────────
type Tab = 'search' | 'pair' | 'stack' | 'library'

export default function App() {
  const [tab, setTab] = useState<Tab>('pair')

  const tabs: { id: Tab; label: string; icon: string }[] = [
    { id: 'search', label: 'Search', icon: '🔍' },
    { id: 'pair', label: 'Pair Checker', icon: '⚗️' },
    { id: 'stack', label: 'Stack Analyser', icon: '🧬' },
    { id: 'library', label: 'Library', icon: '📚' },
  ]

  return (
    <div className="app-container">
      {/* Header */}
      <header className="header">
        <div className="header-logo">⚗️ SuppTracker</div>
        <p className="header-sub">Science-backed supplement interaction analysis</p>
      </header>

      <Legend />

      {/* Tabs */}
      <div className="tabs" style={{ marginBottom: 20 }}>
        {tabs.map(t => (
          <button key={t.id} id={`tab-${t.id}`} className={`tab${tab === t.id ? ' active' : ''}`}
            onClick={() => setTab(t.id)}>
            {t.icon} {t.label}
          </button>
        ))}
      </div>

      {/* Tab panels */}
      <div className="card" style={{ padding: 24 }}>
        {tab === 'search' && <SearchTab />}
        {tab === 'pair' && <PairTab />}
        {tab === 'stack' && <StackTab />}
        {tab === 'library' && <LibraryTab />}
      </div>

      {/* Footer */}
      <footer style={{ textAlign: 'center', marginTop: 40, color: 'var(--text-muted)', fontSize: 12, lineHeight: 1.6 }}>
        SuppTracker is for informational purposes only and does not constitute medical advice.<br />
        Always consult a qualified healthcare professional before changing your supplement regimen.
      </footer>
    </div>
  )
}