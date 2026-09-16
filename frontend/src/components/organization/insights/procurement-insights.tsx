"use client";

import { useState } from "react";
import Link from "next/link";
import { bidStatistics, currentTenderContext, estimatedCost, formatInr, historicalProcurements, historicalStatistics, representativeBids, riskIndicators } from "@/data/procurement-insights";
import styles from "./insights.module.css";

const views = ["Overview", "Historical Intelligence", "Price & Competition", "Risk & Patterns"] as const;
type View = (typeof views)[number];

export function ProcurementInsights() {
  const [view, setView] = useState<View>("Overview");
  return <div className={styles.page}>
    <header className={styles.header}><div><p className={styles.kicker}>Procurement intelligence</p><h1>Procurement Insights</h1><p>Benchmark procurement activity, understand bid pricing and competition, and surface patterns requiring human review.</p></div><div className={styles.context}><small>Analysis context</small><strong>{currentTenderContext.title}</strong><span>{currentTenderContext.reference}</span></div></header>
    <div className={styles.tabs} role="tablist" aria-label="Procurement insight views">{views.map((item) => <button key={item} role="tab" aria-selected={view === item} onClick={() => setView(item)}>{item}</button>)}</div>
    {view === "Overview" && <InsightsOverview onNavigate={setView} />}
    {view === "Historical Intelligence" && <HistoricalIntelligence />}
    {view === "Price & Competition" && <PriceCompetition />}
    {view === "Risk & Patterns" && <RiskPatterns />}
  </div>;
}

function Metric({ label, value, note }: { label: string; value: string; note: string }) { return <article className={styles.metric}><small>{label}</small><strong>{value}</strong><span>{note}</span></article>; }

function InsightsOverview({ onNavigate }: { onNavigate: (view: View) => void }) {
  const apex = representativeBids[0];
  return <div className={styles.stack}>
    <section className={styles.metrics}><Metric label="Estimated Cost" value={formatInr(estimatedCost)} note="Current canonical tender"/><Metric label="Average Representative Bid" value={formatInr(bidStatistics.average)} note="Three canonical bids"/><Metric label="Median Representative Bid" value={formatInr(bidStatistics.median)} note="Deterministic median"/><Metric label="Bid Range" value={formatInr(bidStatistics.spread)} note="Highest minus lowest"/></section>
    <section className={styles.overviewGrid}>
      <article className={styles.panel}><PanelTitle title="Historical Benchmark" eyebrow="Frontend demo benchmark"/><p className={styles.lede}>{historicalStatistics.comparable} comparable procurements show a median award value of <strong>{formatInr(historicalStatistics.medianAward)}</strong> and a typical completion period of {historicalStatistics.typicalCompletion} months.</p><button className={styles.textAction} onClick={() => onNavigate("Historical Intelligence")}>Explore historical intelligence →</button></article>
      <article className={styles.panel}><PanelTitle title="Current Bid Position" eyebrow="Current canonical data"/><p className={styles.lede}>{apex.vendor} is {formatInr(estimatedCost - apex.value)} below the estimated cost. Price position is context only and does not determine the procurement outcome.</p><button className={styles.textAction} onClick={() => onNavigate("Price & Competition")}>Review price intelligence →</button></article>
      <article className={styles.panel}><PanelTitle title="Competition" eyebrow="Representative detailed bids"/><p className={styles.lede}>Three canonical vendor records are shown in detail within a broader demo context of 100 proposals.</p><Link className={styles.textAction} href="/organization/evaluation">View evaluation →</Link></article>
      <article className={`${styles.panel} ${styles.attention}`}><PanelTitle title="Risk Attention" eyebrow="Human review indicators"/><p className={styles.lede}>{riskIndicators.filter((item) => item.status.includes("Review")).length} analytical indicators suggest review. These indicators are not findings or accusations.</p><button className={styles.textAction} onClick={() => onNavigate("Risk & Patterns")}>Open review indicators →</button></article>
    </section>
    <nav className={styles.linkBar} aria-label="Insight links"><Link href="/organization/tenders/bphu">View Tender</Link><Link href="/organization/tenders/bphu">View Tender Blueprint</Link><Link href="/organization/evaluation/apex-infra">View Apex Evaluation</Link><Link href="/organization/vendors/apex-infra">View Apex Vendor</Link></nav>
  </div>;
}

function PanelTitle({ title, eyebrow }: { title: string; eyebrow: string }) { return <header className={styles.panelTitle}><div><small>{eyebrow}</small><h2>{title}</h2></div></header>; }

function HistoricalIntelligence() {
  const [selected, setSelected] = useState<(typeof historicalProcurements)[number]>(historicalProcurements[0]);
  return <div className={styles.stack}>
    <section className={styles.metrics}><Metric label="Comparable Procurements" value={String(historicalStatistics.comparable)} note="Clearly labeled demo records"/><Metric label="Median Award Value" value={formatInr(historicalStatistics.medianAward)} note="Demo historical benchmark"/><Metric label="Median Bidder Count" value={String(historicalStatistics.medianBidders)} note="Across comparable records"/><Metric label="Typical Completion" value={`${historicalStatistics.typicalCompletion} months`} note="Median delivery period"/></section>
    <section className={styles.panel}><PanelTitle title="Similar Procurements" eyebrow="Frontend demo historical records"/><div className={styles.tableWrap}><table><thead><tr><th>Procurement</th><th>Organization</th><th>Estimated</th><th>Award</th><th>Bidders</th><th>Completion</th><th>Similarity</th></tr></thead><tbody>{historicalProcurements.map((record) => <tr key={record.id} className={selected.id === record.id ? styles.selected : ""} onClick={() => setSelected(record)}><td><button className={styles.rowButton} onClick={() => setSelected(record)}>{record.procurement}</button><span>{record.location}</span></td><td>{record.organization}</td><td>{formatInr(record.estimated)}</td><td>{formatInr(record.award)}</td><td>{record.bidders}</td><td>{record.completionMonths} months</td><td><span className={styles.badge}>{record.similarity}</span></td></tr>)}</tbody></table></div></section>
    <section className={styles.compare}><div><PanelTitle title="Current BPHU Tender" eyebrow="Current canonical data"/><dl><dt>Estimated Cost</dt><dd>{formatInr(estimatedCost)}</dd><dt>Category</dt><dd>{currentTenderContext.category}</dd><dt>Location</dt><dd>{currentTenderContext.location}</dd><dt>Completion</dt><dd>{currentTenderContext.completion}</dd></dl></div><div><PanelTitle title={selected.procurement} eyebrow="Selected demo comparison"/><dl><dt>Estimated Value</dt><dd>{formatInr(selected.estimated)}</dd><dt>Award Value</dt><dd>{formatInr(selected.award)}</dd><dt>Bidder Count</dt><dd>{selected.bidders}</dd><dt>Completion</dt><dd>{selected.completionMonths} months</dd></dl></div></section>
    <section className={styles.scenario}><div><small>What-if preview</small><h2>Turnover Requirement Scenario</h2><p>Current requirement: 50% of estimated cost · Potential scenario: 75%</p></div><strong>Analytics engine integration required</strong></section>
  </div>;
}

function PriceCompetition() {
  const max = Math.max(estimatedCost, ...representativeBids.map((bid) => bid.value));
  const rows = [{ vendor: "Estimated Cost", value: estimatedCost, context: "Tender baseline" }, ...representativeBids];
  return <div className={styles.stack}>
    <section className={styles.metrics}><Metric label="Lowest Canonical Bid" value={formatInr(bidStatistics.lowest)} note="Representative detailed bid"/><Metric label="Highest Canonical Bid" value={formatInr(bidStatistics.highest)} note="Representative detailed bid"/><Metric label="Average Bid" value={formatInr(bidStatistics.average)} note="Three canonical bids"/><Metric label="Median Bid" value={formatInr(bidStatistics.median)} note="Deterministic median"/><Metric label="Bid Spread" value={formatInr(bidStatistics.spread)} note="Price dispersion"/></section>
    <section className={styles.panel}><PanelTitle title="Canonical Bid Position" eyebrow="Current canonical data"/><div className={styles.bars}>{rows.map((row) => <div className={styles.barRow} key={row.vendor}><div><strong>{row.vendor}</strong><span>{row.context}</span></div><div className={styles.track}><i style={{ width: `${(row.value / max) * 100}%` }}/></div><b>{formatInr(row.value)}</b></div>)}</div><p className={styles.disclaimer}>Lowest price does not equal procurement winner. Evaluation, compliance, evidence and human decision-making remain separate.</p></section>
    <section className={styles.panel}><PanelTitle title="Bid Position and Evaluation Context" eyebrow="Representative detailed bids"/><div className={styles.tableWrap}><table><thead><tr><th>Vendor</th><th>Bid Value</th><th>Difference vs Estimate</th><th>Relative Position</th><th>Evaluation Context</th></tr></thead><tbody>{[...representativeBids].sort((a,b) => a.value-b.value).map((bid,index) => <tr key={bid.vendor}><td><strong>{bid.vendor}</strong></td><td>{formatInr(bid.value)}</td><td>{formatInr(bid.value-estimatedCost)}</td><td>#{index+1} by price</td><td>{bid.context}</td></tr>)}</tbody></table></div></section>
    <section className={styles.split}><article className={styles.panel}><PanelTitle title="Historical Price Context" eyebrow="Demo historical benchmark data"/><p className={styles.lede}>Demo awards range from {formatInr(historicalStatistics.minAward)} to {formatInr(historicalStatistics.maxAward)}. This range was not queried from a live dataset.</p></article><article className={styles.panel}><PanelTitle title="Competition Context" eyebrow="Portfolio context"/><p className={styles.lede}>100 proposals in the broader demonstration · {historicalStatistics.medianBidders} median historical bidders · {formatInr(bidStatistics.spread)} representative bid spread.</p></article></section>
  </div>;
}

function RiskPatterns() {
  return <div className={styles.stack}>
    <section className={styles.panel}><PanelTitle title="Risk and Review Indicators" eyebrow="Demo analytical indicators for human review"/><div className={styles.tableWrap}><table><thead><tr><th>Indicator</th><th>Entity</th><th>Category</th><th>Reason</th><th>Status</th><th>Review Action</th></tr></thead><tbody>{riskIndicators.map((item) => <tr key={item.indicator}><td><strong>{item.indicator}</strong></td><td>{item.entity}</td><td>{item.category}</td><td>{item.reason}</td><td><span className={styles.badge}>{item.status}</span></td><td>{item.action}</td></tr>)}</tbody></table></div></section>
    <section className={styles.split}><article className={styles.panel}><PanelTitle title="Proposal Similarity" eyebrow="Review dimension"/><div className={styles.signalList}>{[["Methodology Text","Elevated Similarity"],["Document Structure","Review Suggested"],["Pricing Pattern","Moderate"]].map(([a,b]) => <div key={a}><span>{a}</span><strong>{b}</strong></div>)}</div><p className={styles.disclaimer}>Similarity alone does not establish improper coordination and should be reviewed alongside procurement evidence.</p></article><article className={styles.panel}><PanelTitle title="Supplier Concentration" eyebrow="Demo portfolio indicator"/><div className={styles.signalList}>{[["Apex Infra","4 awards · 40% · Review Suggested"],["BuildMax","2 awards · 20% · Low"],["Zenith","1 award · 10% · Low"]].map(([a,b]) => <div key={a}><span>{a}</span><strong>{b}</strong></div>)}</div></article></section>
    <section className={styles.split}><article className={styles.panel}><PanelTitle title="Information Consistency" eyebrow="Cross-record verification"/><div className={styles.signalList}>{[["Registered Company Name","Consistent"],["GST Name","Difference Detected"],["PAN Name","Consistent"],["Company Address","Verification Pending"],["Financial Statement Entity","Requires Review"]].map(([a,b]) => <div key={a}><span>{a}</span><strong>{b}</strong></div>)}</div></article><article className={styles.panel}><PanelTitle title="Procurement Relationships" eyebrow="User-facing relationship view"/><div className={styles.relationships}>{["Organization","Tender","Proposal","Vendor","Certificate","Previous Project","Award"].map((node,index) => <div key={node}><span>{String(index+1).padStart(2,"0")}</span><strong>{node}</strong></div>)}</div><p className={styles.disclaimer}>Relationship structure is a frontend preview; no graph query or automated finding has run.</p></article></section>
  </div>;
}
