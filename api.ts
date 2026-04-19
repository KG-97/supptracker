/// <reference types="vite/client" />
const BASE = (import.meta.env.VITE_API_BASE || "").replace(/\/+$/, "");
const API = `${BASE}/api`;

async function j(res: Response) {
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    let msg = text;
    try {
      const body = JSON.parse(text);
      msg = (body && (body.detail || body.message)) || JSON.stringify(body);
    } catch {}
    throw new Error(`HTTP ${res.status}: ${msg || res.statusText}`);
  }
  return res.json();
}

export async function search(q: string) {
  return j(await fetch(`${API}/search?q=${encodeURIComponent(q)}`));
}

export async function getCompounds() {
  return j(await fetch(`${API}/compounds`));
}

export async function getInteraction(a: string, b: string, opts?: { flags?: string; doses?: string }) {
  const u = new URL(`${API}/interaction`, location.href);
  u.searchParams.set("a", a);
  u.searchParams.set("b", b);
  if (opts?.flags) u.searchParams.set("flags", opts.flags);
  if (opts?.doses) u.searchParams.set("doses", opts.doses);
  return j(await fetch(u.toString()));
}

export async function checkStack(items: string[]) {
  return j(
    await fetch(`${API}/stack/check`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ items }),
    })
  );
}
