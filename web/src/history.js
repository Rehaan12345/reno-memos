// Persistent chat history in localStorage. Each entry stores the full search
// result so an old chat can be reopened without re-calling the API.

const KEY = "reno_chat_history";
const MAX = 50;

export function loadHistory() {
  try {
    return JSON.parse(localStorage.getItem(KEY)) || [];
  } catch {
    return [];
  }
}

// Save a result. De-dupes by question (case-insensitive): asking the same thing
// again moves it to the top rather than creating a duplicate. Returns the id.
export function saveHistory(result) {
  const entry = {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    ts: Date.now(),
    ...result,
  };
  const q = (result.query || "").trim().toLowerCase();
  const rest = loadHistory().filter((e) => (e.query || "").trim().toLowerCase() !== q);
  const next = [entry, ...rest].slice(0, MAX);
  try {
    localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    /* storage full or unavailable — history is best-effort */
  }
  return entry.id;
}

export function getHistoryEntry(id) {
  return loadHistory().find((e) => e.id === id) || null;
}

export function clearHistory() {
  localStorage.removeItem(KEY);
}
