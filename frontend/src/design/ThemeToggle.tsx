import { useState } from "react";

import { Theme, currentTheme, setTheme } from "./theme";

export function ThemeToggle() {
  const [theme, set] = useState<Theme>(currentTheme);
  const next: Theme = theme === "dark" ? "light" : "dark";
  return (
    <button
      type="button"
      className="ghost theme-toggle"
      onClick={() => {
        setTheme(next);
        set(next);
      }}
    >
      {next === "light" ? "Light theme" : "Dark theme"}
    </button>
  );
}
