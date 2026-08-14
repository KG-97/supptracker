import React from 'react'
import { severityBadgeClass, scoreToColor, scoreBarPct } from '../utils/helpers'
import type { InteractionResponse } from '../types'

export default function InteractionResult({ data }: { data: InteractionResponse }) {
  const { pair, interaction: ix } = data
  if (!ix) return null
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
