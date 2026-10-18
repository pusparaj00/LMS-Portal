export type Recent = { href: string; title: string };

const KEY = "lms-recent";
const LIMIT = 5;
export const RECENT_EVENT = "lms-recent";

export function getRecent(): Recent[] {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(KEY) ?? "[]");
    return Array.isArray(parsed) ? (parsed as Recent[]).slice(0, LIMIT) : [];
  } catch {
    return [];
  }
}

function save(items: Recent[]): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(items));
  } catch {
    // the list is a convenience; without storage it stays empty
  }
  window.dispatchEvent(new Event(RECENT_EVENT));
}

export function recordRecent(item: Recent): void {
  save([item, ...getRecent().filter((r) => r.href !== item.href)].slice(0, LIMIT));
}

/** Titles of problems belong to the signed-in person, so logging out clears them. */
export function clearRecent(): void {
  save([]);
}
