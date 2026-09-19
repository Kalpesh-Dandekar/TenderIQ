export type BlueprintCategory = "qualification" | "technical" | "commercial" | "contractual";
export type ReviewState = "ready" | "needs-review" | "reviewed";

export interface EvidenceSource {
  page: number;
  section: string | null;
  excerpt: string;
  interpretation: string;
  evidenceId?: string;
  sourceReference?: string;
  additionalSources?: Array<{ page: number; section: string | null; excerpt: string; sourceReference?: string }>;
}

export interface BlueprintRequirement {
  id: string;
  category: BlueprintCategory;
  title: string;
  description: string;
  mandatory: boolean | null;
  value?: string;
  evidenceExpected?: string[];
  review: ReviewState;
  reviewReason?: string;
  attributes?: Array<{ label: string; value: string }>;
  evidence: EvidenceSource;
}

export interface TechnicalCriterion extends BlueprintRequirement {
  maximumMarks: number | null;
  minimumMarks: number | null;
}

export interface FormulaDefinition {
  label: string;
  expression: string;
  parts: Array<{ label: string; value: string }>;
}

export interface ContractualGroup {
  label: string;
  rules: BlueprintRequirement[];
}

export interface BlueprintPreview {
  dataSource: "preview" | "backend";
  tender: { title: string; reference: string; document: string; pages: number; status: string };
  qualification: BlueprintRequirement[];
  technical: { threshold: number; total: number; criteria: TechnicalCriterion[]; requirements: BlueprintRequirement[] };
  commercial: { financialFormula?: FormulaDefinition; combinedFormula?: FormulaDefinition; rules: BlueprintRequirement[] };
  contractual: ContractualGroup[];
}
