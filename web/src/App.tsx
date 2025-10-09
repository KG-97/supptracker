import React, { useState, useEffect, useCallback } from 'react';
import { searchCompounds, SearchResponse, CompoundMatch } from './api';

function useDebouncedValue<T>(value: T, delay = 250) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return v;
}

function App() {
  const [query, setQuery] = useState('');
  const debouncedQuery = useDebouncedValue(query, 250);
  const [results, setResults] = useState<CompoundMatch[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const doSearch = useCallback(async (q: string) => {
    if (!q || q.trim().length < 1) {
      setResults([]);
      setError(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data: SearchResponse = await searchCompounds(q, 20);
      setResults(data.compounds || []);
    } catch (err: any) {
      console.error('search error', err);
      setError(err?.message || 'Search failed');
      setResults([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    doSearch(debouncedQuery);
  }, [debouncedQuery, doSearch]);

  return (
    <div className="p-4 max-w-2xl mx-auto">
      <h1 className="text-2xl font-bold mb-4">Supplement Interaction Tracker</h1>
      <div className="mb-4">
        <input
          aria-label="Search compounds"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search compounds (e.g. fish oil, caffeine)"
          className="w-full p-2 border rounded"
        />
      </div>

      {loading && <p className="text-sm text-gray-500">Searching...</p>}
      {error && <p className="text-sm text-red-600">{error}</p>}

      {results.length > 0 && (
        <ul className="space-y-2">
          {results.map((r) => (
            <li key={r.id} className="p-2 border rounded">
              <div className="font-semibold">{r.name} <span className="text-xs text-gray-500">({r.score})</span></div>
              {r.synonyms && r.synonyms.length > 0 && (
                <div className="text-sm text-gray-600">Aliases: {r.synonyms.join(', ')}</div>
              )}
            </li>
          ))}
        </ul>
      )}

      {!loading && !error && results.length === 0 && debouncedQuery && (
        <p className="text-sm text-gray-500">No matches</p>
      )}
    </div>
  );
}

export default App;
