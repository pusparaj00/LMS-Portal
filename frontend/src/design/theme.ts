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

/** Dark is the default on a first visit (ux-plan 1.1); a stored choice overrides it. */
export function applyStoredTheme(): void {
  let theme: Theme = "dark";
  try {
    if (localStorage.getItem(KEY) === "light") theme = "light";
  } catch {
    // keep the default
  }
  document.documentElement.dataset.theme = theme;
}
