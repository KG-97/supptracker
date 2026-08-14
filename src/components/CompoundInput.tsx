import React, { useState, useEffect, useRef } from 'react'
import { search } from '../api'
import type { CompoundHit } from '../types'

interface Props {
  id?: string
  value: string
  onChange: (value: string) => void
  placeholder?: string
  onEnter?: () => void
}

export default function CompoundInput({ id, value, onChange, placeholder, onEnter }: Props) {
  const [suggestions, setSuggestions] = useState<CompoundHit[]>([])
  const [showDropdown, setShowDropdown] = useState(false)
  const [activeIndex, setActiveIndex] = useState(-1)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)

    if (!value.trim() || value.trim().length < 2) {
      setSuggestions([])
      setShowDropdown(false)
      return
    }

    debounceRef.current = setTimeout(async () => {
      try {
        const data = await search(value.trim())
        const hits = (data.compounds || []).slice(0, 8)
        setSuggestions(hits)
        setShowDropdown(hits.length > 0)
        setActiveIndex(-1)
      } catch {
        setSuggestions([])
        setShowDropdown(false)
      }
    }, 250)

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [value])

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setShowDropdown(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const selectItem = (item: CompoundHit) => {
    onChange(item.id)
    setShowDropdown(false)
    setSuggestions([])
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!showDropdown || suggestions.length === 0) {
      if (e.key === 'Enter' && onEnter) onEnter()
      return
    }

    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActiveIndex(prev => (prev + 1) % suggestions.length)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActiveIndex(prev => (prev <= 0 ? suggestions.length - 1 : prev - 1))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      if (activeIndex >= 0 && activeIndex < suggestions.length) {
        selectItem(suggestions[activeIndex])
      } else if (onEnter) {
        setShowDropdown(false)
        onEnter()
      }
    } else if (e.key === 'Escape') {
      setShowDropdown(false)
    }
  }

  return (
    <div ref={containerRef} className="autocomplete-container">
      <input
        id={id}
        className="input"
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        onKeyDown={handleKeyDown}
        onFocus={() => suggestions.length > 0 && setShowDropdown(true)}
        autoComplete="off"
      />
      {showDropdown && (
        <div className="autocomplete-dropdown">
          {suggestions.map((item, i) => (
            <div
              key={item.id}
              className={`autocomplete-item${i === activeIndex ? ' active' : ''}`}
              onMouseDown={(e) => { e.preventDefault(); selectItem(item) }}
              onMouseEnter={() => setActiveIndex(i)}
            >
              <span className="autocomplete-name">{item.name}</span>
              <span className="autocomplete-id">{item.id}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
