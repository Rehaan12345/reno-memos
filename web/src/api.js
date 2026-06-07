// Thin client over the FastAPI backend. Every call returns parsed JSON or throws.

async function get(path) {
  const res = await fetch(path);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail || detail;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail);
  }
  return res.json();
}

export const api = {
  stats: () => get("/api/stats"),
  search: (q) => get(`/api/search?q=${encodeURIComponent(q)}`),
  threads: () => get("/api/threads"),
  flags: () => get("/api/flags"),
  metrics: () => get("/api/metrics"),
  decisions: () => get("/api/decisions"),
  memo: (id) => get(`/api/memo/${encodeURIComponent(id)}`),
};
