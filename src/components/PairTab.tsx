import React, { useState } from 'react'
import { getInteraction } from '../api'
import Spinner from './Spinner'
import InteractionResult from './InteractionResult'
import CompoundInput from './CompoundInput'
import type { InteractionResponse } from '../types'

export default function PairTab() {
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
        <CompoundInput id="pair-a" value={a} onChange={setA}
          placeholder="Compound A — e.g. caffeine" onEnter={check} />
        <div className="pair-cross">×</div>
        <CompoundInput id="pair-b" value={b} onChange={setB}
          placeholder="Compound B — e.g. magnesium" onEnter={check} />
        <button id="pair-check-btn" className="btn btn-primary" onClick={check} disabled={loading}>
          {loading ? <Spinner /> : 'Check'}
        </button>
      </div>
      {error && <div className="error-box" style={{ marginTop: 12 }}>{error}</div>}
      {result && !result.found && (
        <div className="no-data-state" style={{ marginTop: 16, padding: '20px 24px', borderRadius: 'var(--r-lg)', background: 'rgba(255,255,255,0.03)', border: '1px solid var(--border)', textAlign: 'center', animation: 'fadeSlideIn 0.3s ease both' }}>
          <div style={{ fontSize: 28, marginBottom: 8 }}>🔬</div>
          <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4 }}>
            No interaction data available
          </div>
          <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.5 }}>
            We don't have interaction data for <strong>{result.pair.a}</strong> × <strong>{result.pair.b}</strong> yet.<br />
            This doesn't necessarily mean they're safe to combine — consult a healthcare professional.
          </div>
        </div>
      )}
      {result && result.found && result.interaction && <InteractionResult data={result} />}
    </div>
  )
}
