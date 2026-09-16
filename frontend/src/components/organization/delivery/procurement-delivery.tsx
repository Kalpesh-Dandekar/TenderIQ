"use client";

import { useState } from "react";
import Link from "next/link";
import { completionEvidence, deliveryMetrics, deliveryStages, demoAwardScenario, invoiceMatch, milestones, supplierPerformance } from "@/data/procurement-delivery";
import styles from "./delivery.module.css";

const views = ["Overview", "Awards & Contracts", "Orders & Fulfilment", "Invoices & Performance"] as const;
type View = (typeof views)[number];

export function ProcurementDelivery() {
  const [view, setView] = useState<View>("Overview");
  return <div className={styles.page}>
    <header className={styles.header}><div><p className={styles.kicker}>Procurement delivery</p><h1>Procurement Delivery</h1><p>Manage procurement awards, contractual commitments, fulfilment, invoice validation and supplier performance.</p></div><div className={styles.demo}><small>Demo Award Scenario</small><strong>{demoAwardScenario.tender}</strong><span>Simulated TenderIQ workflow · not a historical award claim</span></div></header>
    <div className={styles.tabs} role="tablist" aria-label="Procurement delivery views">{views.map((item) => <button key={item} role="tab" aria-selected={view === item} onClick={() => setView(item)}>{item}</button>)}</div>
    {view === "Overview" && <DeliveryOverview onNavigate={setView}/>} {view === "Awards & Contracts" && <AwardsContracts/>} {view === "Orders & Fulfilment" && <OrdersFulfilment/>} {view === "Invoices & Performance" && <InvoicesPerformance/>}
  </div>;
}

function Title({ title, context }: { title: string; context: string }) { return <header className={styles.panelTitle}><small>{context}</small><h2>{title}</h2></header>; }
function Status({ children }: { children: string }) { return <span className={styles.status}>{children}</span>; }

function DeliveryOverview({ onNavigate }: { onNavigate: (view: View) => void }) {
  return <div className={styles.stack}>
    <section className={styles.metrics}>{deliveryMetrics.map(([label,value]) => <article key={label}><small>{label}</small><strong>{value}</strong><span>Frontend demo portfolio</span></article>)}</section>
    <section className={styles.panel}><Title title="Procurement Delivery Pipeline" context="Post-award lifecycle"/><div className={styles.pipeline}>{deliveryStages.map((stage,index) => <div key={stage}><span>{String(index+1).padStart(2,"0")}</span><strong>{stage}</strong></div>)}</div></section>
    <section className={styles.grid}><article className={styles.panel}><Title title="BPHU Demo Award" context={demoAwardScenario.label}/><dl className={styles.details}><dt>Demo Awarded Vendor</dt><dd>{demoAwardScenario.vendor}</dd><dt>Award Value</dt><dd>{demoAwardScenario.awardValue}</dd><dt>Award Status</dt><dd><Status>{demoAwardScenario.awardStatus}</Status></dd><dt>Contract</dt><dd>{demoAwardScenario.contractStatus}</dd></dl><button className={styles.action} onClick={() => onNavigate("Awards & Contracts")}>Open award and contract →</button></article><article className={styles.panel}><Title title="Current Delivery Attention" context="Simulated review state"/><div className={styles.attention}><div><strong>Foundation milestone</strong><span>Measurement record pending</span></div><Status>Pending Verification</Status><div><strong>Invoice INV-DEMO-1042</strong><span>Completion evidence needs review</span></div><Status>Requires Review</Status></div><button className={styles.action} onClick={() => onNavigate("Invoices & Performance")}>Review invoice matching →</button></article></section>
    <Links/>
  </div>;
}

function AwardsContracts() {
  return <div className={styles.stack}><section className={styles.notice}><strong>Demo Award Scenario</strong><span>This simulated TenderIQ post-award state does not represent the historical outcome of the referenced tender.</span></section><section className={styles.panel}><Title title="Award and Contract Record" context="Simulated post-award record"/><div className={styles.recordGrid}>{[["Tender",demoAwardScenario.tender],["Vendor",demoAwardScenario.vendor],["Award Value",demoAwardScenario.awardValue],["Award / LOI Status",demoAwardScenario.awardStatus],["Contract Status",demoAwardScenario.contractStatus],["Start",demoAwardScenario.start],["Target Completion",demoAwardScenario.targetCompletion],["Performance Security",demoAwardScenario.performanceSecurity]].map(([label,value]) => <article key={label}><small>{label}</small><strong>{value}</strong></article>)}</div></section><section className={styles.grid}><article className={styles.panel}><Title title="Contract Commitments" context="Compact monitoring"/><div className={styles.progress}><div><span>Contract progress</span><strong>18% · Demo record</strong></div><i><b style={{width:"18%"}}/></i></div><dl className={styles.details}><dt>Completion Period</dt><dd>{demoAwardScenario.completion}</dd><dt>Pending Obligations</dt><dd>Measurement submission</dd><dt>Contract Alert</dt><dd>Evidence due before milestone certification</dd></dl></article><article className={styles.panel}><Title title="Key Milestones" context="Construction contract"/><div className={styles.list}>{milestones.slice(0,3).map((item) => <div key={item.name}><span><strong>{item.name}</strong><small>{item.target}</small></span><Status>{item.status}</Status></div>)}</div></article></section><Links/></div>;
}

function OrdersFulfilment() {
  return <div className={styles.stack}><section className={styles.panel}><Title title="Contract / Work Order" context="Frontend demo record"/><div className={styles.recordGrid}>{[["Work Order ID",demoAwardScenario.workOrder],["Tender",demoAwardScenario.tender],["Vendor",demoAwardScenario.vendor],["Value",demoAwardScenario.awardValue],["Issue Date",demoAwardScenario.issueDate],["Status","Active · Demo"]].map(([label,value]) => <article key={label}><small>{label}</small><strong>{value}</strong></article>)}</div></section><section className={styles.panel}><Title title="Construction Milestones" context="Services and works fulfilment"/><div className={styles.milestones}>{milestones.map((item,index) => <article key={item.name}><span>{String(index+1).padStart(2,"0")}</span><div><strong>{item.name}</strong><small>Target · {item.target}</small><p>{item.evidence}</p></div><Status>{item.status}</Status></article>)}</div></section><section className={styles.panel}><Title title="Receipt / Completion Evidence" context="Evidence register"/><div className={styles.evidence}>{completionEvidence.map(([name,status]) => <div key={name}><strong>{name}</strong><Status>{status}</Status></div>)}</div><p className={styles.note}>Construction uses milestone, measurement, inspection and acceptance evidence rather than assuming a goods receipt process.</p></section><Links/></div>;
}

function InvoicesPerformance() {
  return <div className={styles.stack}><section className={styles.panel}><Title title="Three-Way Matching" context="Construction and services semantics"/><div className={styles.match}>{invoiceMatch.map((item,index) => <article key={item.source}><span>{String(index+1).padStart(2,"0")}</span><small>{item.source}</small><strong>{item.reference}</strong><b>{item.amount}</b><p>{item.evidence}</p><Status>{item.status}</Status></article>)}</div><div className={styles.readiness}><div><small>Payment readiness</small><strong>Ready for Finance Review</strong></div><p>Finance and procurement approval remains a human responsibility. No payment has been approved automatically.</p></div></section><section className={styles.grid}><article className={styles.panel}><Title title="Supplier Performance" context="Demo supplier performance record"/><div className={styles.performance}>{supplierPerformance.map(([dimension,value]) => <div key={dimension}><span>{dimension}</span><strong>{value}</strong></div>)}</div></article><article className={styles.panel}><Title title="Contract / SLA Monitoring" context="Compact architecture preview"/><dl className={styles.details}><dt>Contract Progress</dt><dd>18% · Demo</dd><dt>Milestones</dt><dd>1 complete · 1 active · 3 upcoming</dd><dt>Target Completion</dt><dd>{demoAwardScenario.targetCompletion}</dd><dt>Pending Obligation</dt><dd>Measurement evidence</dd><dt>Alert</dt><dd>Review before invoice certification</dd></dl></article></section><Links/></div>;
}

function Links() { return <nav className={styles.links} aria-label="Delivery links"><Link href="/organization/tenders/bphu">View Tender</Link><Link href="/organization/vendors/apex-infra">View Vendor</Link><Link href="/organization/evaluation/apex-infra">View Evaluation</Link><Link href="/organization/insights">View Procurement Insights</Link></nav>; }
