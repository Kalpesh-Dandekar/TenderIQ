import { bphuTender, vendors } from "@/data/demo-procurement";

export const formatInr = (value: number) => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(value);

export const estimatedCost = 5_453_776;
export const representativeBids = vendors.slice(0, 3).map((vendor) => ({
  vendor: vendor.name,
  value: Number(vendor.bid.replace(/[^0-9]/g, "")),
  context: vendor.id === "apex-infra" ? "Strong evidence coverage" : vendor.id === "buildmax" ? "Evidence gap requires review" : "Multiple evidence and compliance gaps",
}));

const sortedBids = representativeBids.map((bid) => bid.value).sort((a, b) => a - b);
export const bidStatistics = {
  average: Math.round(sortedBids.reduce((sum, value) => sum + value, 0) / sortedBids.length),
  median: sortedBids[1],
  lowest: sortedBids[0],
  highest: sortedBids[sortedBids.length - 1],
  spread: sortedBids[sortedBids.length - 1] - sortedBids[0],
};

export const historicalProcurements = [
  { id: "hist-01", procurement: "Community Health Centre Expansion", organization: "Odisha Health Infrastructure Agency", location: "Keonjhar, Odisha", estimated: 5_820_000, award: 5_410_000, bidders: 8, completionMonths: 4, similarity: "High" },
  { id: "hist-02", procurement: "Primary Care Facility Construction", organization: "District Health Society", location: "Mayurbhanj, Odisha", estimated: 5_140_000, award: 4_880_000, bidders: 6, completionMonths: 3, similarity: "High" },
  { id: "hist-03", procurement: "Rural Health Unit Civil Works", organization: "Public Works Division", location: "Sambalpur, Odisha", estimated: 6_210_000, award: 5_760_000, bidders: 7, completionMonths: 5, similarity: "Medium" },
  { id: "hist-04", procurement: "Block Clinic Building Works", organization: "State Medical Corporation", location: "Kalahandi, Odisha", estimated: 5_530_000, award: 5_190_000, bidders: 5, completionMonths: 4, similarity: "High" },
  { id: "hist-05", procurement: "Public Health Centre Upgrade", organization: "Urban Health Mission", location: "Cuttack, Odisha", estimated: 4_760_000, award: 4_520_000, bidders: 9, completionMonths: 3, similarity: "Medium" },
  { id: "hist-06", procurement: "District Clinic Rehabilitation", organization: "Engineering Projects Division", location: "Koraput, Odisha", estimated: 5_970_000, award: 5_620_000, bidders: 6, completionMonths: 5, similarity: "Medium" },
] as const;

const median = (values: number[]) => { const sorted = [...values].sort((a, b) => a - b); return (sorted[2] + sorted[3]) / 2; };
export const historicalStatistics = {
  comparable: historicalProcurements.length,
  medianAward: median(historicalProcurements.map((record) => record.award)),
  medianBidders: median(historicalProcurements.map((record) => record.bidders)),
  typicalCompletion: median(historicalProcurements.map((record) => record.completionMonths)),
  minAward: Math.min(...historicalProcurements.map((record) => record.award)),
  maxAward: Math.max(...historicalProcurements.map((record) => record.award)),
};

export const riskIndicators = [
  { indicator: "Pricing deviation", entity: "Zenith", category: "Pricing Patterns", reason: "Bid is materially below the current estimate and requires commercial context.", status: "Review Suggested", action: "Review cost basis" },
  { indicator: "Proposal similarity", entity: "BuildMax / Zenith", category: "Proposal Similarity", reason: "Selected document sections share elevated structural similarity.", status: "Review Suggested", action: "Compare source files" },
  { indicator: "Supplier concentration", entity: "Demo portfolio", category: "Supplier Concentration", reason: "A small supplier group represents a notable share of demo awards.", status: "Moderate", action: "Monitor portfolio share" },
  { indicator: "Document inconsistency", entity: "BuildMax", category: "Information Consistency", reason: "One registered entity field differs across submitted records.", status: "Verification Pending", action: "Verify registration" },
  { indicator: "Evidence gap", entity: "Zenith", category: "Evidence Completeness", reason: "Multiple mandatory evidence references remain incomplete.", status: "Requires Review", action: "Open evaluation" },
] as const;

export const currentTenderContext = { title: bphuTender.shortTitle, reference: bphuTender.reference, category: bphuTender.category, location: bphuTender.location, completion: bphuTender.completion };
