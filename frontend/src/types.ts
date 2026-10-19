export type DiagnosticItem = {
  problem_id: number;
  kind: "code" | "mcq";
  title: string;
  statement: string;
  options: { id: number; text: string }[];
};

export type ConceptMastery = {
  concept_id: number;
  name: string;
  p_known: number;
  status?: "assessed" | "estimated" | "not assessed" | null;
  confidence?: "low" | "moderate" | "higher" | null;
  evidence_count?: number | null;
  last_assessed?: string | null;
};

export type Misconception = { name: string; description: string; probability: number };

export type DiagnosticResult = {
  mastery: ConceptMastery[];
  misconceptions: Misconception[];
  ability: number;
};

export type DiagnosticStep = {
  session_id: string;
  item_number: number;
  next_item: DiagnosticItem | null;
  done: boolean;
  result: DiagnosticResult | null;
};

export type DiagnosticStart = {
  session_id: string;
  item_number: number;
  max_items: number;
  item: DiagnosticItem;
};

export type Dashboard = {
  concepts: ConceptMastery[];
  misconceptions: Misconception[];
  recent_submissions: {
    submission_id: number;
    problem_id: number;
    problem_title: string;
    status: string;
    passed: number;
    failed: number;
    created_at: string;
  }[];
  recommended: { problem_id: number; title: string; reason: string } | null;
  placement_completed: boolean;
  placement_available: boolean;
};

export type LedgerEntry = {
  created_at: string;
  concept: string;
  p_before: number;
  p_after: number;
  evidence_type: string;
  rule_id: string;
  explanation: string;
  submission_id: number | null;
};
