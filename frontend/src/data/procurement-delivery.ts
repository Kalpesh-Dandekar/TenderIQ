import { bphuTender, vendors } from "@/data/demo-procurement";

const apex = vendors[0];
export const demoAwardScenario = {
  label: "Simulated TenderIQ post-award scenario",
  tender: bphuTender.shortTitle,
  reference: bphuTender.reference,
  vendor: apex.name,
  awardValue: apex.bid,
  awardStatus: "Award Acknowledged",
  contractStatus: "In Progress",
  workOrder: "WO-BPHU-DEMO-001",
  issueDate: "16 Sep 2026",
  start: "21 Sep 2026",
  targetCompletion: "20 Dec 2026",
  performanceSecurity: bphuTender.performanceSecurity,
  completion: bphuTender.completion,
} as const;

export const deliveryMetrics = [
  ["Active Contracts", "04"], ["Open Work Orders", "07"], ["Pending Milestones", "05"], ["Invoices Requiring Review", "03"],
] as const;

export const deliveryStages = ["Award", "Contract / LOI", "Work Order", "Milestone", "Completion Evidence", "Invoice", "Matching", "Finance Review", "Supplier Performance"] as const;

export const milestones = [
  { name: "Site Mobilization", target: "28 Sep 2026", status: "Completed", evidence: "Mobilization record received" },
  { name: "Foundation / Structural Stage", target: "24 Oct 2026", status: "In Progress", evidence: "Measurement record pending" },
  { name: "Building Works", target: "20 Nov 2026", status: "Upcoming", evidence: "Not yet due" },
  { name: "Electrical & Plumbing", target: "08 Dec 2026", status: "Upcoming", evidence: "Not yet due" },
  { name: "Final Inspection / Handover", target: "20 Dec 2026", status: "Pending Verification", evidence: "Inspection and acceptance required" },
] as const;

export const completionEvidence = [
  ["Inspection Report", "Pending Verification"], ["Measurement / Completion Record", "Received"], ["Acceptance Record", "Requires Review"], ["Site Progress Record", "Verified"],
] as const;

export const invoiceMatch = [
  { source: "Work Order", reference: "WO-BPHU-DEMO-001", amount: apex.bid, evidence: "Signed work order", status: "Matched" },
  { source: "Milestone Evidence", reference: "MS-02 / Foundation", amount: "₹10,46,200", evidence: "Measurement record pending", status: "Partial Match" },
  { source: "Vendor Invoice", reference: "INV-DEMO-1042", amount: "₹10,46,200", evidence: "Invoice copy received", status: "Requires Review" },
] as const;

export const supplierPerformance = [
  ["Milestone Adherence", "On track"], ["Quality", "Inspection pending"], ["Compliance", "Requirements met to date"], ["Responsiveness", "Within agreed timelines"],
] as const;
