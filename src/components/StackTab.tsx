import React, { useState } from 'react'
import { checkStack } from '../api'
import Spinner from './Spinner'
import { severityBadgeClass, bucketCellClass, scoreToColor } from '../utils/helpers'
import type { StackCell, StackResponse } from '../types'

export default function StackTab() {
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
