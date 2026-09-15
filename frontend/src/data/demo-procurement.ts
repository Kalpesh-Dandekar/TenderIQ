// Frontend presentation data for procurement workflow prototypes. Replace with API data later.
export const bphuTender = {
  id: "bphu", title: "Construction of Block Primary Health Unit (BPHU) Building",
  shortTitle: "BPHU Building Tender", reference: "PCO/BBSR/953/144",
  organization: "Engineering Projects (India) Limited", location: "Lahunipada, Sundergarh District, Odisha",
  type: "Percentage Rate", category: "Construction", bidProcess: "Single-stage two-bid",
  estimatedCost: "₹54,53,776 excluding GST", completion: "3 months", emd: "₹1,09,076",
  fee: "₹11,800", validity: "90 days", performanceSecurity: "5%",
  submission: "19 Dec 2023, 03:00 PM", opening: "20 Dec 2023, 03:00 PM", stage: "Under Evaluation",
  turnoverThreshold: "₹27.27L",
} as const;

export const tenders = [
  bphuTender,
  { id:"it-modernization", title:"IT Infrastructure Modernization", shortTitle:"IT Infrastructure", reference:"TIQ/IT/2026/041", organization:"Central Administration", location:"Bhubaneswar, Odisha", type:"Item Rate", category:"Technology", bidProcess:"Two-bid", estimatedCost:"₹1,28,00,000", completion:"6 months", emd:"₹2,56,000", fee:"₹14,000", validity:"120 days", performanceSecurity:"5%", submission:"23 Sep 2026, 05:00 PM", opening:"24 Sep 2026, 11:00 AM", stage:"Published", turnoverThreshold:"₹64.00L" },
  { id:"medical-equipment", title:"District Medical Equipment Supply", shortTitle:"Medical Equipment", reference:"TIQ/MED/2026/018", organization:"Regional Healthcare Network", location:"Sundergarh, Odisha", type:"Supply", category:"Medical Supply", bidProcess:"Single-stage two-bid", estimatedCost:"₹76,40,000", completion:"90 days", emd:"₹1,52,800", fee:"₹11,800", validity:"90 days", performanceSecurity:"5%", submission:"Review complete", opening:"Completed", stage:"Completed", turnoverThreshold:"₹38.20L" },
  { id:"water-rehab", title:"Rural Water Supply Rehabilitation", shortTitle:"Water Supply", reference:"TIQ/CIV/2026/063", organization:"District Infrastructure Cell", location:"Keonjhar, Odisha", type:"Percentage Rate", category:"Civil Works", bidProcess:"Two-bid", estimatedCost:"₹92,10,000", completion:"8 months", emd:"₹1,84,200", fee:"₹11,800", validity:"90 days", performanceSecurity:"5%", submission:"Draft", opening:"—", stage:"Draft", turnoverThreshold:"₹46.05L" },
] as const;

export const bphuRequirements = [
  { category:"Experience", id:"EXP-01", title:"Similar work during last 7 years", rule:"3 works ≥ 40% OR 2 works ≥ 60% OR 1 work ≥ 80%", detail:"Scope includes non-residential building, electrical work and plumbing work." },
  { category:"Financial Capacity", id:"FIN-01", title:"Minimum Average Annual Turnover", rule:"≥ ₹27.27L", detail:"At least 50% of estimated cost across 3 financial years." },
  { category:"Financial Capacity", id:"FIN-02", title:"Banker Certificate or Net Worth", rule:"Banker ≥ 40% OR Net Worth ≥ 10%", detail:"Evidence required for the selected financial capacity route." },
  { category:"Legal & Registration", id:"LEG-01", title:"Statutory registrations", rule:"PAN · GST · PF Registration", detail:"Valid registration evidence must accompany the proposal." },
] as const;

export const bphuDocuments = ["Tender Fee / EMD","Power of Attorney","Affidavits","Site Visit Declaration","Constitution Documents","Similar Work Evidence","Audited Financial Statements","Turnover Certificate","Banker Certificate OR Net Worth Certificate","PAN","GST","PF Registration"] as const;
export const blueprintRecords = [
  { id:"FIN-01", category:"Financial Capacity", title:"Minimum Average Annual Turnover", operator:">=", required:"₹27.27L", period:"3 financial years", evidence:"Audited Financial Statements · Turnover Certificate", source:"Pre-Qualification Criteria", mandatory:"Yes" },
  { id:"EXP-01", category:"Experience", title:"Similar Completed Works", operator:"OR rule", required:"3×40% · 2×60% · 1×80%", period:"Last 7 years", evidence:"Work orders · Completion certificates", source:"Eligibility Criteria", mandatory:"Yes" },
] as const;

export const vendors = [
  { id:"apex-infra", name:"Apex Infra", bid:"₹52,31,000", participation:"BPHU + 2", activeBids:3, documentStatus:"Externally Verified", awards:4, performance:"Strong", risk:"Low Risk", eligibility:"Compliant", technical:"Strong", financial:"Compliant", compliance:"Compliant", evidence:"96%", rank:1, status:"Shortlisted" },
  { id:"buildmax", name:"BuildMax", bid:"₹50,75,000", participation:"BPHU + 1", activeBids:2, documentStatus:"Verification Pending", awards:2, performance:"Good", risk:"Evidence Gap", eligibility:"Requires Review", technical:"Good", financial:"Compliant", compliance:"Evidence Missing", evidence:"84%", rank:2, status:"Review" },
  { id:"zenith", name:"Zenith", bid:"₹47,85,000", participation:"BPHU", activeBids:1, documentStatus:"Suspicious — Requires Review", awards:1, performance:"Mixed", risk:"Requires Human Review", eligibility:"Non-Compliant", technical:"Requires Review", financial:"Evidence Missing", compliance:"Non-Compliant", evidence:"61%", rank:7, status:"Review" },
  { id:"eastern-builders", name:"Eastern Builders", bid:"₹53,10,000", participation:"BPHU + 3", activeBids:4, documentStatus:"Validated", awards:3, performance:"Good", risk:"Low Risk", eligibility:"Compliant", technical:"Good", financial:"Compliant", compliance:"Compliant", evidence:"91%", rank:3, status:"Evaluated" },
  { id:"odisha-civil", name:"Odisha Civil Works", bid:"₹53,84,500", participation:"BPHU + 1", activeBids:2, documentStatus:"Likely Authentic", awards:2, performance:"Good", risk:"Review Suggested", eligibility:"Compliant", technical:"Good", financial:"Compliant", compliance:"Requires Review", evidence:"87%", rank:4, status:"Evaluated" },
  { id:"northstar-projects", name:"Northstar Projects", bid:"₹54,02,000", participation:"BPHU", activeBids:1, documentStatus:"Unable to Verify", awards:0, performance:"New", risk:"Review Suggested", eligibility:"Requires Review", technical:"Good", financial:"Requires Review", compliance:"Compliant", evidence:"79%", rank:5, status:"Review" },
] as const;

export const apexDocuments = [
  { document:"PAN", identifier:"AAECA4821D", validity:"Active", state:"Externally Verified", checked:"14 Sep 2026" },
  { document:"GST", identifier:"21AAECA4821D1ZK", validity:"Active", state:"Externally Verified", checked:"14 Sep 2026" },
  { document:"PF Registration", identifier:"OR/BBS/18402", validity:"Active", state:"Validated", checked:"13 Sep 2026" },
  { document:"Turnover Certificate", identifier:"FY21–FY23", validity:"Current", state:"Validated", checked:"13 Sep 2026" },
  { document:"Audited Financial Statements", identifier:"3 financial years", validity:"Current", state:"Likely Authentic", checked:"12 Sep 2026" },
  { document:"Similar Work Certificate", identifier:"SWC-04", validity:"Accepted", state:"Validated", checked:"12 Sep 2026" },
] as const;
