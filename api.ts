const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000/api';

async function parseError(res: Response, fallback: string) {
  try {
    const text = (await res.text()).trim();
    if (!text) return fallback;
    try {
      const data = JSON.parse(text);
      if (typeof data === 'string') return data;
      if (data && typeof data.message === 'string') return data.message;
      if (data && typeof data.detail === 'string') return data.detail;
      if (data && typeof data.error === 'string') return data.error;
      return text;
    } catch {
      return text;
    }
  } catch {
    return fallback;
  }
}

export async function search(q: string) {
  const res = await fetch(`${API_BASE}/search?q=${encodeURIComponent(q)}`);
  if (!res.ok) throw new Error(await parseError(res, 'search failed'));
  return res.json();
}

export async function getInteraction(a: string, b: string) {
  const res = await fetch(`${API_BASE}/interaction?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`);
  if (!res.ok) throw new Error(await parseError(res, 'pair not found'));
  return res.json();
}

export async function checkStack(compounds: string[]) {
  const res = await fetch(`${API_BASE}/stack/check`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ compounds }),
  });
  if (!res.ok) throw new Error(await parseError(res, 'stack check failed'));
  return res.json();
}
