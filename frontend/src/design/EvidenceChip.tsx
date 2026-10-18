import { ReactNode } from "react";

/** Mono text for one piece of evidence, such as "test #17, empty_input". A link when it has somewhere to go. */
export function EvidenceChip({ children, href }: { children: ReactNode; href?: string }) {
  return href ? (
    <a className="evidence" href={href}>
      {children}
    </a>
  ) : (
    <span className="evidence">{children}</span>
  );
}
