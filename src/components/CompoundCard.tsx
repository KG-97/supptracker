import React from 'react'
import { classEmoji } from '../utils/helpers'
import type { CompoundDetail } from '../types'

export default function CompoundCard({ c }: { c: CompoundDetail }) {
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
