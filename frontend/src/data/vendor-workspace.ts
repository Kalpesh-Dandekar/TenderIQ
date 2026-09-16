import { apexDocuments, bphuDocuments, bphuRequirements, bphuTender, tenders, vendors } from "@/data/demo-procurement";

export const apex = vendors[0];
export const vendorTender = bphuTender;
export const opportunities = [
  bphuTender,
  ...tenders.slice(1),
  { id:"solar-clinics", title:"Solar Power Systems for Rural Clinics", shortTitle:"Rural Clinic Solar", reference:"TIQ/ENE/2026/029", organization:"State Renewable Mission", location:"Odisha", type:"Supply & Installation", category:"Energy", bidProcess:"Two-bid", estimatedCost:"₹64,20,000", completion:"4 months", emd:"₹1,28,400", fee:"₹11,800", validity:"90 days", performanceSecurity:"5%", submission:"30 Sep 2026, 05:00 PM", opening:"01 Oct 2026, 11:00 AM", stage:"Published", turnoverThreshold:"₹32.10L" },
] as const;
export const proposal = { value: apex.bid, status:"Draft · In Preparation", readiness:"Ready for Final Review", documents:"11 of 12 ready", evidence:"94% demo coverage", updated:"16 Sep 2026", version:"Draft v1" } as const;
export const eligibility = [
  ["EXP-01","Similar work in previous 7 years","3 works ≥40% OR 2 works ≥60% OR 1 work ≥80%","Evidence Available","Similar Work Certificate"],
  ["FIN-01","Average annual turnover","≥ ₹27.27L across previous 3 years","Ready","Turnover Certificate"],
  ["FIN-02","Financial capacity","Banker ≥ ₹21.82L OR Net Worth ≥ ₹5.45L","Ready","Banker's Certificate"],
  ["FIN-03","Financial loss","No losses in more than 2 of relevant 5 years","Review Required","Audited Statements"],
  ["LEG-01","Statutory registrations","PAN · GST · PF","Ready","Document Vault"],
] as const;
export const requiredDocuments = [...bphuDocuments, "Covering Letter", "Non-blacklisting Declaration", "Form of Tender", "Manpower / Equipment Information"] as const;
export const vaultDocuments = [
  ...apexDocuments.map((d,index)=>({ id:`vault-${index}`, name:d.document, category:index<3?"Business & Registration":index<5?"Financial":"Experience", identifier:d.identifier, validity:d.validity, status:index===4?"Verification Pending":"Validated", usedIn:index>2?"BPHU Proposal · FIN-01":"BPHU Proposal", updated:d.checked })),
  { id:"banker",name:"Banker's Certificate",category:"Financial",identifier:"BC-2026-18",validity:"Current",status:"Ready",usedIn:"BPHU Proposal · FIN-02",updated:"12 Sep 2026" },
  { id:"completion",name:"Work Order / Completion Evidence",category:"Experience",identifier:"SWC-04 bundle",validity:"Accepted",status:"Validated",usedIn:"BPHU Proposal · EXP-01",updated:"11 Sep 2026" },
] as const;
export const proposalBlueprint = [
  ["CLM-01","FIN-01","Average Annual Turnover ₹68.0L","Turnover Certificate","Page 14","Mapped"],
  ["CLM-02","EXP-01","One similar completed healthcare building project","Similar Work Certificate","Pages 8–11","Mapped"],
  ["CLM-03","LEG-01","Active PAN, GST and PF registrations","Registration bundle","Pages 21–28","Mapped"],
] as const;
export const auditItems = [["Eligibility Readiness","Ready"],["Mandatory Documents","Ready"],["Evidence Coverage","Ready"],["Proposal Completeness","Requires Review"],["Submission Conditions","Ready"]] as const;
export const vendorRequirements = bphuRequirements;

export const bidActivity = {
  submittedVersion:"v1", bidValue:apex.bid, submissionState:"Demo Submission State", submittedAt:"16 Sep 2026, 04:15 PM · Simulated", procurementStage:"Technical Review", lockState:"Locked After Submission", integrity:"Backend integrity record pending integration",
} as const;
export const reviewProgress = [["Submission Received","Complete"],["Document Review","Complete"],["Technical Review","In Progress"],["Financial Review","Pending"],["Compliance Review","Pending"],["Decision","Pending"]] as const;
export const clarification = { id:"CLAR-BPHU-01", subject:"Similar-work completion evidence", requestedBy:"Procurement Organization", requestedDate:"17 Sep 2026", deadline:"20 Sep 2026, 05:00 PM", status:"Clarification Required", requirement:"EXP-01", request:"Please provide the completion certificate supporting the referenced similar-work claim." } as const;
export const demoAward = { label:"Demo Award Scenario", value:apex.bid, notification:"Award / LOI Received", acknowledgement:"Awaiting Acknowledgement", contract:"Preparation In Progress", workOrder:"WO-BPHU-DEMO-001", start:"21 Sep 2026", target:"20 Dec 2026", performanceSecurity:vendorTender.performanceSecurity, completion:vendorTender.completion } as const;
export const vendorMilestones = [["Site Mobilization","Completed"],["Foundation / Structural Stage","In Progress"],["Building Works","Upcoming"],["Electrical & Plumbing","Upcoming"],["Final Inspection / Handover","Pending Verification"]] as const;
export const vendorInvoices = [["INV-DEMO-1042","Foundation milestone","₹10,46,200","16 Oct 2026","Partial Match","Ready for Finance Review"]] as const;
