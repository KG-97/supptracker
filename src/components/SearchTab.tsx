import React, { useState, useRef } from 'react'
import { search } from '../api'
import Spinner from './Spinner'
import type { CompoundHit } from '../types'

export default function SearchTab() {
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
