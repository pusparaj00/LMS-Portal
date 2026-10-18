import { createRoot } from "react-dom/client";

import { App } from "./App";
import "@fontsource/instrument-sans/latin-400.css";
import "@fontsource/instrument-sans/latin-500.css";
import "@fontsource/instrument-sans/latin-600.css";
import "@fontsource/jetbrains-mono/latin-400.css";
import "@fontsource/jetbrains-mono/latin-600.css";
import "./styles.css";
import "./design/design.css";
import { applyStoredTheme } from "./design/theme";

applyStoredTheme();

createRoot(document.getElementById("root")!).render(<App />);
