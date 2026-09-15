// Presentation-only overview data. Replace with API data when backend modules are enabled.
export const overviewMetrics = [
  { label: "Active Tenders", value: "8", detail: "Across 4 procurement stages", tone: "active" },
  { label: "Proposals Received", value: "126", detail: "Evidence intake recorded", tone: "neutral" },
  { label: "Under Evaluation", value: "3", detail: "Specialist review in progress", tone: "review" },
  { label: "Pending Decisions", value: "2", detail: "Procurement action required", tone: "warning" },
] as const;

export const activeTenders = [
  { title: "Construction of Block Primary Health Unit (BPHU)", location: "Lahunipada, Sundergarh District, Odisha", reference: "PCO/BBSR/953/144", stage: "Evaluation", deadline: "18 Sep 2026", proposals: 100, evaluation: "84 processed" },
  { title: "IT Infrastructure Modernization", location: "Central Administration Campus", reference: "TIQ/IT/2026/041", stage: "Receiving Bids", deadline: "23 Sep 2026", proposals: 18, evaluation: "Intake open" },
  { title: "Medical Equipment Supply", location: "Regional Healthcare Network", reference: "TIQ/MED/2026/018", stage: "Award Pending", deadline: "Review due", proposals: 8, evaluation: "Final validation" },
] as const;

export const attentionItems = [
  { count: "02", title: "Submission deadlines approaching", context: "IT Infrastructure · Civil Works", tone: "warning" },
  { count: "01", title: "Evaluation awaiting procurement review", context: "BPHU Building Tender", tone: "review" },
  { count: "03", title: "Vendor clarifications pending", context: "Across two active tenders", tone: "neutral" },
  { count: "01", title: "Final decision required", context: "Medical Equipment Supply", tone: "warning" },
] as const;

export const evaluationAgents = [
  { name: "Technical Agent", status: "Complete", progress: 100 },
  { name: "Financial Agent", status: "Complete", progress: 100 },
  { name: "Compliance Agent", status: "Processing", progress: 72 },
] as const;

export const pipelineStages = [
  { label: "Tender", value: "08" }, { label: "Bidding", value: "05" },
  { label: "Evaluation", value: "03" }, { label: "Decision", value: "02" },
  { label: "Delivery", value: "—" },
] as const;

export const recentActivity = [
  { time: "11:42", event: "Vendor proposal submitted", context: "IT Infrastructure · Nexa Systems" },
  { time: "10:18", event: "Tender Blueprint generated", context: "Water Supply Rehabilitation" },
  { time: "09:36", event: "Compliance review completed", context: "BPHU · Proposal 072" },
  { time: "Yesterday", event: "Clarification received", context: "Medical Equipment · Medline India" },
] as const;
