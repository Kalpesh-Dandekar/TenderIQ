import { SectionHeading } from "./shared";

const capabilities = [
  { number: "01", title: "Procurement Planning", copy: "Create or upload tenders, then transform complex documents into structured requirements.", meta: ["Tender intake", "Requirement design", "Document control"], className: "" },
  { number: "02", title: "Digital Bidding", copy: "A controlled path from tender discovery to evidence-backed proposal submission.", meta: ["Participation", "Proposal workspace"], className: "" },
  { number: "03", title: "Procurement Intelligence", copy: "Map every requirement to evidence, source references, and deterministic checks.", meta: ["Tender Blueprint", "Evidence mapping"], className: "capability--accent" },
  { number: "04", title: "Decision Intelligence", copy: "Bring technical, financial, and compliance findings into an explainable decision record.", meta: ["Evaluation", "Comparison", "Validation"], className: "" },
];
export function Capabilities() { return <section className="section section-grid" id="platform"><div className="container"><SectionHeading eyebrow="One connected platform" title={<>Four systems. <span className="muted-title">One evidence chain.</span></>} copy="TenderIQ connects procurement planning, bidding, verification, and evaluation without losing the thread between requirement and decision." /><div className="capability-grid">{capabilities.map((item) => <article className={`capability ${item.className}`} key={item.number}><div className="capability-top"><span>{item.number}</span><i /></div><h3>{item.title}</h3><p>{item.copy}</p><div className="capability-meta">{item.meta.map((meta) => <span key={meta}>{meta}</span>)}</div></article>)}</div></div></section>; }
