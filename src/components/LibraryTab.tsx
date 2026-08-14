import React, { useState, useEffect } from 'react'
import { getCompounds } from '../api'
import Spinner from './Spinner'
import CompoundCard from './CompoundCard'
import type { CompoundDetail } from '../types'

export default function LibraryTab() {
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
      {loading && (
        <div className="compound-grid">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="compound-card" style={{ padding: 16 }}>
              <div className="skeleton skeleton-line" style={{ width: '70%', height: 16 }} />
              <div className="skeleton skeleton-line" style={{ width: '40%', height: 12, marginTop: 8 }} />
              <div className="skeleton skeleton-line" style={{ width: '90%', height: 12, marginTop: 12 }} />
              <div className="skeleton skeleton-line" style={{ width: '50%', height: 12 }} />
            </div>
          ))}
        </div>
      )}
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
