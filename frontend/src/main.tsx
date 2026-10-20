import { createRoot } from "react-dom/client";

import { App } from "./App";
import "@fontsource/bricolage-grotesque/latin-400.css";
import "@fontsource/bricolage-grotesque/latin-500.css";
import "@fontsource/bricolage-grotesque/latin-600.css";
import "@fontsource/jetbrains-mono/latin-400.css";
import "@fontsource/jetbrains-mono/latin-600.css";
import "./styles.css";
import "./design/design.css";
import { applyStoredTheme } from "./design/theme";

applyStoredTheme();

createRoot(document.getElementById("root")!).render(<App />);
