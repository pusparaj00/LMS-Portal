import type { EditorProps } from "@monaco-editor/react";
import { Suspense, lazy, useEffect, useState } from "react";

import { Theme, currentTheme } from "../design/theme";

// Loaded on first use, so the public pages do not download the editor.
const MonacoEditor = lazy(() => import("./MonacoEditor"));

/** The code editor in the app's current theme, following the toggle. */
export function CodeEditor(props: EditorProps) {
  const [theme, setTheme] = useState<Theme>(currentTheme);
  useEffect(() => {
    const observer = new MutationObserver(() => setTheme(currentTheme()));
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => observer.disconnect();
  }, []);
  return (
    <Suspense fallback={<p>Loading the editor…</p>}>
      <MonacoEditor theme={theme === "dark" ? "vs-dark" : "light"} {...props} />
    </Suspense>
  );
}
