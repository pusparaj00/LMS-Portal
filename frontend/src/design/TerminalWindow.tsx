import { ReactNode } from "react";

/** A product preview in app chrome: a mono title bar and an optional tag such as "Sample data" (ux-plan 1.3). */
export function TerminalWindow({ title, tag, children }: { title: string; tag?: string; children: ReactNode }) {
  return (
    <div className="terminal">
      <div className="terminal-bar">
        <span className="terminal-title">{title}</span>
        {tag && <span className="terminal-tag">{tag}</span>}
      </div>
      <div className="terminal-body">{children}</div>
    </div>
  );
}
