export type BackendRequirementCategory =
  | "ELIGIBILITY" | "TECHNICAL" | "FINANCIAL" | "DOCUMENT"
  | "COMMERCIAL" | "CONTRACTUAL" | "SECURITY" | "OTHER";

export interface BackendSourceReference {
  page_number: number;
  section: string | null;
  clause: string | null;
  excerpt: string;
}

export interface BackendNormalizedRequirement {
  value: string | number | boolean | null;
  operator: "=" | ">=" | ">" | "<=" | "<" | null;
  unit: string | null;
  currency: string | null;
  period: string | null;
}

export interface BackendTenderRequirement {
  requirement_id: string;
  category: BackendRequirementCategory;
  raw_text: string;
  normalized_text: string;
  requirement_type: string;
  mandatory: boolean | null;
  normalized: BackendNormalizedRequirement;
  expected_evidence: string[];
  source_references: BackendSourceReference[];
  confidence: number;
  requires_review: boolean;
}

export interface BackendEvaluationCriterion {
  criterion_id: string;
  name: string;
  raw_rule: string;
  maximum_score: number | null;
  minimum_score: number | null;
  weight_percent: number | null;
  formula: string | null;
  disqualification_condition: string | null;
  source_references: BackendSourceReference[];
  confidence: number;
  requires_review: boolean;
}

export interface BackendEvaluationStage {
  stage_id: string;
  name: string;
  sequence: number;
  stage_type: string;
  raw_rule: string | null;
  minimum_score: number | null;
  weight_percent: number | null;
  formula: string | null;
  disqualification_conditions: string[];
  criteria: BackendEvaluationCriterion[];
  source_references: BackendSourceReference[];
  confidence: number;
  requires_review: boolean;
}

export interface BackendTenderBlueprint {
  schema_version: string;
  source_filename: string;
  source_sha256: string;
  metadata: {
    title: string | null;
    reference_number: string | null;
    issuing_organization: string | null;
    tender_type: string | null;
    contract_type: string | null;
    submission_mode: string | null;
    currency: string | null;
    important_dates: unknown[];
    bid_validity: string | null;
    bid_security: string | null;
    tender_fee: string | null;
    performance_security: string | null;
  };
  requirements: BackendTenderRequirement[];
  required_documents: unknown[];
  evaluation_stages: BackendEvaluationStage[];
}

export interface BackendBlueprintResponse {
  success: true;
  blueprint: BackendTenderBlueprint;
  grounded_semantics?: BackendGroundedSemantics | null;
}

interface BackendGroundedItem {
  source_references: BackendSourceReference[];
  candidate_ids: string[];
  requires_review: boolean;
  review_reason: string | null;
}

export interface BackendGroundedQualificationRequirement extends BackendGroundedItem {
  requirement_id: string;
  category: BackendRequirementCategory;
  requirement_type: string;
  title: string;
  requirement_text: string;
  mandatory: boolean | null;
  normalized: BackendNormalizedRequirement;
}

export interface BackendGroundedTechnicalRequirement extends BackendGroundedItem {
  requirement_id: string;
  kind: "SCORED_CRITERION" | "OVERALL_THRESHOLD" | "TECHNICAL_REQUIREMENT";
  title: string;
  description: string;
  mandatory: boolean | null;
  maximum_marks: number | null;
  minimum_qualifying_marks: number | null;
  threshold_value: number | null;
  threshold_operator: "=" | ">=" | ">" | "<=" | "<" | null;
  weight_percent: number | null;
  expected_evidence: string[];
}

export interface BackendGroundedCommercialFinancialRule extends BackendGroundedItem {
  rule_id: string;
  kind: "FINANCIAL_SCORE_FORMULA" | "WEIGHTED_SCORE_FORMULA" | "COMMERCIAL_RULE" | "FINANCIAL_REQUIREMENT";
  title: string;
  description: string;
  mandatory: boolean | null;
  formula_expression: string | null;
  formula_variables: string[];
  formula_semantics: string | null;
  formula_multiplier: number | null;
  technical_weight_percent: number | null;
  financial_weight_percent: number | null;
  percentage_value: number | null;
  money_value: string | null;
  currency: string | null;
  operator: "=" | ">=" | ">" | "<=" | "<" | null;
  unit: string | null;
  expected_evidence: string[];
}

export interface BackendGroundedContractualRule extends BackendGroundedItem {
  rule_id: string;
  kind: string;
  title: string;
  description: string;
  responsible_party: string | null;
  beneficiary_or_counterparty: string | null;
  obligation_semantics: "MUST" | "MUST_NOT" | "MAY" | "SHOULD" | "CONDITIONAL" | "RIGHT" | null;
  action_or_obligation: string | null;
  condition: string | null;
  operator: "=" | ">=" | ">" | "<=" | "<" | null;
  numeric_value: number | null;
  percentage_value: number | null;
  money_value: string | null;
  currency: string | null;
  duration_value: number | null;
  duration_unit: string | null;
  deadline_or_timing: string | null;
  consequence_or_remedy: string | null;
  mandatory: boolean | null;
  expected_evidence: string[];
}

export interface BackendGroundedSemantics {
  qualification_requirements: BackendGroundedQualificationRequirement[];
  technical_requirements: BackendGroundedTechnicalRequirement[];
  commercial_financial_rules: BackendGroundedCommercialFinancialRule[];
  contractual_rules: BackendGroundedContractualRule[];
}
