const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000/api';

export async function search(q: string) {
  const res = await fetch(`${API_BASE}/search?q=${encodeURIComponent(q)}`);
  if (!res.ok) throw new Error('search failed');
  return res.json();
}

export async function getInteraction(a: string, b: string) {
  const res = await fetch(`${API_BASE}/interaction?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`);
  if (!res.ok) throw new Error('pair not found');
  return res.json();
}

export async function checkStack(compounds: string[]) {
  const res = await fetch(`${API_BASE}/stack/check`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ compounds }),
  });
  if (!res.ok) throw new Error('stack check failed');
  return res.json();
}
