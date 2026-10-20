export type Theme = "dark" | "light";

const KEY = "lms-theme";

export function currentTheme(): Theme {
  return document.documentElement.dataset.theme === "light" ? "light" : "dark";
}

export function setTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
  try {
    localStorage.setItem(KEY, theme);
  } catch {
    // storage can be blocked; the choice then lasts until the page closes
  }
}

/** The first visit follows the system setting; a stored choice overrides it. */
export function applyStoredTheme(): void {
  let theme: Theme = window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  try {
    const stored = localStorage.getItem(KEY);
    if (stored === "light" || stored === "dark") theme = stored;
  } catch {
    // keep the system setting
  }
  document.documentElement.dataset.theme = theme;
}
