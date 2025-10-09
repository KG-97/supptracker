// Lightweight typed API helper with dual-route failover and timeout
export type CompoundMatch = {
  id: string;
  name: string;
  synonyms: string[];
  score?: number;
  match_type?: string;
};

export type SearchResponse = { compounds: CompoundMatch[] };

const TIMEOUT = 8000;

async function fetchWithTimeout(input: RequestInfo, init?: RequestInit, timeout = TIMEOUT) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  try {
    const resp = await fetch(input, { ...(init || {}), signal: controller.signal });
    return resp;
  } finally {
    clearTimeout(timer);
  }
}

async function tryEndpoints(path: string, init?: RequestInit) {
  // Try /api/... first, then fallback to bare path
  const candidates = [`/api${path}`, path];
  let lastErr: any = null;
  for (const p of candidates) {
    try {
      const resp = await fetchWithTimeout(p, init);
      if (!resp.ok) {
        const text = await resp.text();
        throw new Error(`HTTP ${resp.status}: ${text}`);
      }
      return resp;
    } catch (err) {
      lastErr = err;
      // try next
    }
  }
  throw lastErr;
}

export async function searchCompounds(q: string, limit = 20): Promise<SearchResponse> {
  const url = `/search?q=${encodeURIComponent(q)}&limit=${limit}`;
  const resp = await tryEndpoints(url);
  return resp.json();
}

export async function stackCheck(compounds: string[]) {
  const url = `/stack/check`;
  const resp = await tryEndpoints(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ compounds }),
  });
  return resp.json();
}
