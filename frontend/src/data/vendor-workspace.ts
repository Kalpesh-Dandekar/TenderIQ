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
