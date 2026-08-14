import React from 'react'

export default function Legend() {
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
