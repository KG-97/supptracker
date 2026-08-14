import React, { useState } from 'react'
import SearchTab from './src/components/SearchTab'
import PairTab from './src/components/PairTab'
import StackTab from './src/components/StackTab'
import LibraryTab from './src/components/LibraryTab'
import Legend from './src/components/Legend'

// ── App Shell ─────────────────────────────────────────────────────────────────
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