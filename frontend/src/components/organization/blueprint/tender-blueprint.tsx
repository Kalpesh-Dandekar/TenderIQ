"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { allPreviewRequirements, previewBlueprint } from "./preview-data";
import { mapBackendBlueprint } from "./backend-adapter";
import { readBackendBlueprint } from "@/lib/tender-blueprint-session";
import type { BlueprintPreview, BlueprintRequirement, ContractualGroup, FormulaDefinition, ReviewState, TechnicalCriterion } from "./types";
import styles from "./blueprint.module.css";

type View = "qualification" | "technical" | "commercial" | "contractual" | "review";
export type BlueprintPageState = "loading" | "processing" | "available" | "empty" | "error";
const views: Array<{ id: View; label: string }> = [
  {id:"qualification",label:"Qualification"},{id:"technical",label:"Technical"},
  {id:"commercial",label:"Commercial & Financial"},{id:"contractual",label:"Contractual & Other"},{id:"review",label:"Needs Review"},
];
const processingSteps = ["Document Uploaded","Document Intelligence","Evidence Analysis","Blueprint Generated"];
const processingMessages = ["Reading tender document","Identifying procurement requirements","Reconstructing evaluation structure","Linking source evidence","Preparing Blueprint"];

export function TenderBlueprint({initialState="available",dataSource="preview"}:{initialState?:BlueprintPageState;dataSource?:"preview"|"backend"}) {
  const [pageState,setPageState]=useState<BlueprintPageState>(initialState);
  const [blueprint,setBlueprint]=useState<BlueprintPreview>(previewBlueprint);
  const [processingStep,setProcessingStep]=useState(0);
  const [active,setActive]=useState<View>("qualification");
  const [filter,setFilter]=useState<"all"|"mandatory"|"review">("all");
  const [query,setQuery]=useState("");
  const [selected,setSelected]=useState<BlueprintRequirement|null>(null);
  const [reviewStates,setReviewStates]=useState<Record<string,ReviewState>>({});
  const [confirmOpen,setConfirmOpen]=useState(false);
  const [confirmed,setConfirmed]=useState(false);
  const requirements=useMemo(()=>allPreviewRequirements(blueprint),[blueprint]);
  const stateFor=(item:BlueprintRequirement)=>reviewStates[item.id]??item.review;
  const unresolved=requirements.filter(item=>stateFor(item)==="needs-review");

  useEffect(()=>{
    if(dataSource!=="backend")return;
    let active=true;
    queueMicrotask(()=>{
      if(!active)return;
      const response=readBackendBlueprint();
      if(!response){setPageState("empty");return}
      try{setBlueprint(mapBackendBlueprint(response));setPageState("available")}catch{setPageState("error")}
    });
    return()=>{active=false};
  },[dataSource]);
  useEffect(()=>{
    if(pageState!=="processing") return;
    const timer=window.setInterval(()=>setProcessingStep(step=>{
      if(step>=processingMessages.length-1){window.clearInterval(timer);window.setTimeout(()=>setPageState("available"),650);return step} return step+1;
    }),650);
    return()=>window.clearInterval(timer);
  },[pageState]);
  useEffect(()=>{
    if(!confirmOpen)return;
    const close=(event:KeyboardEvent)=>{if(event.key==="Escape")setConfirmOpen(false)};
    document.addEventListener("keydown",close);document.body.style.overflow="hidden";
    return()=>{document.removeEventListener("keydown",close);document.body.style.overflow=""};
  },[confirmOpen]);

  const visible=(items:BlueprintRequirement[])=>items.filter(item=>{
    const text=`${item.title} ${item.description} ${item.value??""}`.toLowerCase();
    return text.includes(query.toLowerCase())&&(filter==="all"||(filter==="mandatory"&&item.mandatory)||(filter==="review"&&stateFor(item)==="needs-review"));
  });
  const openReview=()=>{setActive("review");setFilter("review");document.getElementById("blueprint-content")?.scrollIntoView({behavior:"smooth"})};

  if(pageState==="loading")return <StatePanel title="Loading Blueprint" copy="Preparing the structured procurement workspace." kind="loading" onAction={()=>setPageState("available")}/>;
  if(pageState==="empty")return <StatePanel title="No Blueprint Generated" copy="Analyze a tender document to create a grounded evaluation specification." action="Analyze Tender" onAction={()=>setPageState("processing")}/>;
  if(pageState==="error")return <StatePanel title="Analysis could not be completed" copy="The preview could not prepare this Blueprint. Your source document is unchanged." action="Retry analysis" onAction={()=>{setProcessingStep(0);setPageState("processing")}}/>;
  if(pageState==="processing")return <Processing step={processingStep}/>;
  if(selected)return <EvidenceWorkspace item={selected} document={blueprint.tender.document} state={stateFor(selected)} onBack={()=>setSelected(null)} onReviewed={()=>{setReviewStates(current=>({...current,[selected.id]:"reviewed"}));setSelected(null)}}/>;

  return <div className={styles.page}>
    <header className={styles.hero}>
      <div className={styles.heroCopy}><div className={styles.eyebrow}><span>Tender intelligence</span><Status tone={confirmed?"confirmed":"generated"}>{confirmed?"Blueprint Confirmed":blueprint.tender.status}</Status></div><h1>Tender Blueprint</h1><h2>{blueprint.tender.title}</h2><p>Structured procurement requirements extracted from the tender document and linked to source evidence.</p><div className={styles.sourceLine}><DocumentIcon/><span>{blueprint.tender.document}</span><i/> <span>{blueprint.tender.reference}</span><i/><span>{blueprint.dataSource==="backend"?"Backend Blueprint":"Preview data"}</span></div></div>
      <div className={styles.heroActions}><button className={styles.secondaryButton} type="button" onClick={openReview}>Review Flagged Items <b>{unresolved.length}</b></button><button className={styles.secondaryButton} type="button" onClick={()=>setSelected(requirements[0])}>View Source Document</button><button className="button" type="button" onClick={()=>setConfirmOpen(true)} disabled={confirmed}>{confirmed?"Blueprint Confirmed":"Confirm Blueprint"}</button></div>
    </header>
    {confirmed?<section className={styles.confirmedBanner}><CheckIcon/><div><strong>Blueprint Confirmed</strong><p>This Blueprint will serve as the common evaluation specification for vendor proposals.</p></div><span>Evaluation specification locked</span></section>:null}
    <section className={styles.summary} aria-label="Blueprint summary">
      <SummaryItem label="Pages analyzed" value={blueprint.tender.pages?String(blueprint.tender.pages):"—"} detail={blueprint.tender.document}/>
      <SummaryItem label="Requirements" value={String(requirements.length)} detail="Across the complete Blueprint"/>
      <SummaryItem label="Intelligence categories" value="4" detail="Qualification through contractual"/>
      <SummaryItem label="Evidence coverage" value="Grounded" detail="Page-level source traceability" accent/>
      <SummaryItem label="Needs review" value={String(unresolved.length)} detail="Human acknowledgement required" warning={unresolved.length>0}/>
    </section>
    <div className={styles.workspaceNav}>
      <div className={styles.tabs} role="tablist" aria-label="Blueprint categories">{views.map(view=><button key={view.id} role="tab" aria-selected={active===view.id} onClick={()=>{setActive(view.id);if(view.id!=="review"&&filter==="review")setFilter("all")}}>{view.label}{view.id==="review"?<span>{unresolved.length}</span>:null}</button>)}</div>
      <div className={styles.tools}><label className={styles.search}><SearchIcon/><span className={styles.srOnly}>Search Blueprint</span><input value={query} onChange={event=>setQuery(event.target.value)} placeholder="Search requirements"/></label><div className={styles.filters} aria-label="Requirement filters">{(["all","mandatory","review"] as const).map(item=><button key={item} aria-pressed={filter===item} onClick={()=>setFilter(item)}>{item==="all"?"All":item==="mandatory"?"Mandatory":"Needs Review"}</button>)}</div></div>
    </div>
    <main id="blueprint-content" className={styles.content}>
      {active==="qualification"?<Qualification items={visible(blueprint.qualification)} stateFor={stateFor} onEvidence={setSelected}/>:null}
      {active==="technical"?<Technical technical={blueprint.technical} items={visible(blueprint.technical.criteria) as TechnicalCriterion[]} requirements={visible(blueprint.technical.requirements)} stateFor={stateFor} onEvidence={setSelected}/>:null}
      {active==="commercial"?<Commercial commercial={blueprint.commercial} rules={visible(blueprint.commercial.rules)} stateFor={stateFor} onEvidence={setSelected}/>:null}
      {active==="contractual"?<Contractual groups={blueprint.contractual.map(group=>({...group,rules:visible(group.rules)})).filter(group=>group.rules.length)} stateFor={stateFor} onEvidence={setSelected}/>:null}
      {active==="review"?<ReviewQueue items={visible(unresolved)} stateFor={stateFor} onEvidence={setSelected}/>:null}
    </main>
    {confirmOpen?<ConfirmDialog unresolved={unresolved.length} onClose={()=>setConfirmOpen(false)} onReview={()=>{setConfirmOpen(false);openReview()}} onConfirm={()=>{setConfirmed(true);setConfirmOpen(false);window.scrollTo({top:0,behavior:"smooth"})}}/>:null}
  </div>;
}

function Status({children,tone}:{children:string;tone:"generated"|"confirmed"}){return <span className={`${styles.status} ${tone==="confirmed"?styles.statusConfirmed:""}`}><i/>{children}</span>}
function SummaryItem({label,value,detail,accent,warning}:{label:string;value:string;detail:string;accent?:boolean;warning?:boolean}){return <article className={styles.summaryItem}><small>{label}</small><strong className={accent?styles.accent:warning?styles.warning:""}>{value}</strong><p>{detail}</p></article>}

function Qualification({items,stateFor,onEvidence}:{items:BlueprintRequirement[];stateFor:(i:BlueprintRequirement)=>ReviewState;onEvidence:(i:BlueprintRequirement)=>void}){return <section><SectionHeading eyebrow="Eligibility structure" title="Qualification requirements" copy="Mandatory eligibility criteria, normalized thresholds and expected vendor evidence." count={items.length}/><div className={styles.requirementList}>{items.map(item=><RequirementCard key={item.id} item={item} state={stateFor(item)} onEvidence={onEvidence}/>)}</div>{!items.length?<EmptyResults/>:null}</section>}
function Technical({technical,items,requirements,stateFor,onEvidence}:{technical:BlueprintPreview["technical"];items:TechnicalCriterion[];requirements:BlueprintRequirement[];stateFor:(i:BlueprintRequirement)=>ReviewState;onEvidence:(i:BlueprintRequirement)=>void}){const progress=technical.total?Math.min(100,technical.threshold/technical.total*100):0;return <section><SectionHeading eyebrow="Evaluation specification" title="Technical evaluation" copy="Scored criteria reconstructed from the tender evaluation matrix." count={items.length+requirements.length}/>{technical.threshold||technical.total?<div className={styles.threshold}><div><small>Overall Technical Qualification</small><strong>{technical.threshold}<span> / {technical.total} minimum</span></strong></div><div className={styles.thresholdBar}><i style={{width:`${progress}%`}}/></div><span>Minimum qualifying score</span></div>:null}<div className={styles.matrixWrap}><table className={styles.matrix}><thead><tr><th>Evaluation criterion</th><th>Max score</th><th>Min score</th><th>Source</th><th>Status</th><th/></tr></thead><tbody>{items.map(item=><tr key={item.id}><td><strong>{item.title}</strong><span>{item.description}</span></td><td><b>{item.maximumMarks??"—"}</b></td><td><b>{item.minimumMarks??"—"}</b></td><td><Source item={item}/></td><td><ReviewBadge state={stateFor(item)}/></td><td><button className={styles.textButton} onClick={()=>onEvidence(item)}>View Evidence</button></td></tr>)}</tbody></table></div>{requirements.length?<div className={styles.subsection}><h3>Non-scored technical requirements</h3>{requirements.map(item=><RequirementCard key={item.id} item={item} state={stateFor(item)} onEvidence={onEvidence}/>)}</div>:null}</section>}
function Commercial({commercial,rules,stateFor,onEvidence}:{commercial:BlueprintPreview["commercial"];rules:BlueprintRequirement[];stateFor:(i:BlueprintRequirement)=>ReviewState;onEvidence:(i:BlueprintRequirement)=>void}){const formulas=[commercial.financialFormula,commercial.combinedFormula].filter((formula):formula is FormulaDefinition=>Boolean(formula));return <section><SectionHeading eyebrow="Evaluation economics" title="Commercial & financial" copy="Financial scoring, weighted consolidation and commercial submission rules." count={rules.length+formulas.length}/>{formulas.length?<div className={styles.formulaGrid}>{formulas.map((formula,index)=><Formula key={`${formula.label}-${index}`} formula={formula} kicker={index?"Combined evaluation":"Financial evaluation"} emphasis={index===1}/>)}</div>:null}<div className={styles.subsection}><h3>Commercial requirements</h3><div className={styles.requirementList}>{rules.map(item=><RequirementCard key={item.id} item={item} state={stateFor(item)} onEvidence={onEvidence}/>)}</div>{!rules.length?<EmptyResults/>:null}</div></section>}
function Formula({formula,kicker,emphasis}:{formula:FormulaDefinition;kicker:string;emphasis?:boolean}){return <article className={`${styles.formula} ${emphasis?styles.formulaEmphasis:""}`}><small>{kicker}</small><h3>{formula.label}</h3><div className={styles.expression}>{formula.expression}</div><div className={styles.formulaParts}>{formula.parts.map(part=><span key={part.label}><small>{part.label}</small><strong>{part.value}</strong></span>)}</div></article>}
function Contractual({groups,stateFor,onEvidence}:{groups:ContractualGroup[];stateFor:(i:BlueprintRequirement)=>ReviewState;onEvidence:(i:BlueprintRequirement)=>void}){return <section><SectionHeading eyebrow="Obligation framework" title="Contractual & other" copy="Grouped delivery, service, payment, remedy and governance obligations." count={groups.reduce((sum,g)=>sum+g.rules.length,0)}/><div className={styles.contractGroups}>{groups.map(group=><section className={styles.contractGroup} key={group.label}><header><h3>{group.label}</h3><span>{group.rules.length} {group.rules.length===1?"rule":"rules"}</span></header>{group.rules.map(item=><RequirementCard key={item.id} item={item} state={stateFor(item)} onEvidence={onEvidence} compact/>)}</section>)}</div>{!groups.length?<EmptyResults/>:null}</section>}
function ReviewQueue({items,stateFor,onEvidence}:{items:BlueprintRequirement[];stateFor:(i:BlueprintRequirement)=>ReviewState;onEvidence:(i:BlueprintRequirement)=>void}){return <section><SectionHeading eyebrow="Human review" title="Items requiring review" copy="Resolve grounded ambiguities before confirming the shared evaluation specification." count={items.length}/>{items.length?<div className={styles.requirementList}>{items.map(item=><RequirementCard key={item.id} item={item} state={stateFor(item)} onEvidence={onEvidence}/>)}</div>:<div className={styles.allReviewed}><CheckIcon/><h3>Review queue complete</h3><p>All flagged interpretations have been reviewed.</p></div>}</section>}

function SectionHeading({eyebrow,title,copy,count}:{eyebrow:string;title:string;copy:string;count:number}){return <header className={styles.sectionHeading}><div><small>{eyebrow}</small><h2>{title}</h2><p>{copy}</p></div><span>{count} items</span></header>}
function RequirementCard({item,state,onEvidence,compact}:{item:BlueprintRequirement;state:ReviewState;onEvidence:(i:BlueprintRequirement)=>void;compact?:boolean}){return <article className={`${styles.requirement} ${state==="needs-review"?styles.requirementReview:""} ${compact?styles.requirementCompact:""}`}><div className={styles.requirementMain}><div className={styles.requirementMeta}><span>{item.id}</span><Badge mandatory={item.mandatory}/><ReviewBadge state={state}/></div><h3>{item.title}</h3><p>{item.description}</p>{item.value?<strong className={styles.structuredValue}>{item.value}</strong>:null}{item.evidenceExpected?.length?<div className={styles.evidenceExpected}><small>Expected vendor evidence</small><span>{item.evidenceExpected.join(" · ")}</span></div>:null}</div><div className={styles.requirementSide}><Source item={item}/><button className={styles.evidenceButton} type="button" onClick={()=>onEvidence(item)}>View Evidence <ArrowIcon/></button></div></article>}
function Badge({mandatory}:{mandatory:boolean|null}){return <span className={mandatory?styles.mandatory:styles.optional}>{mandatory===true?"Mandatory":mandatory===false?"Conditional":"Unspecified"}</span>}
function ReviewBadge({state}:{state:ReviewState}){return <span className={`${styles.reviewBadge} ${state==="needs-review"?styles.needsReview:state==="reviewed"?styles.reviewed:""}`}>{state==="needs-review"?"Needs Review":state==="reviewed"?"Reviewed":"Ready"}</span>}
function Source({item}:{item:BlueprintRequirement}){return <span className={styles.source}>Page {item.evidence.page} <i/> {item.evidence.section??"Section not provided"}</span>}
function EmptyResults(){return <div className={styles.emptyResults}>No Blueprint requirements match the current search and filter.</div>}

function EvidenceWorkspace({item,document,state,onBack,onReviewed}:{item:BlueprintRequirement;document:string;state:ReviewState;onBack:()=>void;onReviewed:()=>void}){const section=item.evidence.section??"Section not provided";return <section className={styles.evidenceWorkspace} aria-labelledby="evidence-title"><button className={styles.backToBlueprint} type="button" onClick={onBack}>← Back to Blueprint</button><header className={styles.evidenceHeader}><div><small>Source → Interpretation</small><h1 id="evidence-title">Evidence trace</h1><div className={styles.evidenceIdentity}><span>{item.id}</span><Badge mandatory={item.mandatory}/><ReviewBadge state={state}/></div><h2>{item.title}</h2><Source item={item}/></div>{state==="needs-review"?<button className="button" type="button" onClick={onReviewed}><CheckIcon/>Mark Reviewed</button>:null}</header><div className={styles.evidenceColumns}><div className={styles.sourceColumn}><div className={styles.columnLabel}><span>01</span><div><small>Source</small><strong>Grounded tender evidence</strong></div></div><section className={styles.evidenceBlock}><small>Source evidence</small><div className={styles.pageMarker}>Page {item.evidence.page}<span>{section}</span></div><blockquote>{item.evidence.excerpt}</blockquote></section><div className={styles.sourceMetadata}><div><span>Document</span><strong>{document}</strong></div><div><span>Page</span><strong>{item.evidence.page}</strong></div><div><span>Section</span><strong>{section}</strong></div></div><details className={styles.provenance}><summary>Advanced provenance</summary><dl><div><dt>Rule ID</dt><dd>{item.id}</dd></div>{item.evidence.evidenceId?<div><dt>Evidence ID</dt><dd>{item.evidence.evidenceId}</dd></div>:null}{item.evidence.sourceReference?<div><dt>Source reference</dt><dd>{item.evidence.sourceReference}</dd></div>:null}{item.evidence.additionalSources?.map((source,index)=><div key={`${source.page}-${index}`}><dt>Additional source</dt><dd>Page {source.page} · {source.section??"Section not provided"} · {source.excerpt}</dd></div>)}</dl></details></div><div className={styles.interpretationColumn}><div className={styles.columnLabel}><span>02</span><div><small>Interpretation</small><strong>Structured Blueprint rule</strong></div></div>{state==="needs-review"?<section className={styles.reviewCallout}><small>Why review is required</small><p>{item.reviewReason??"A detailed review reason was not supplied."}</p></section>:null}<section className={styles.interpretation}><small>TenderIQ interpretation</small><p>{item.evidence.interpretation}</p>{item.value?<div><span>Structured value</span><strong>{item.value}</strong></div>:null}{item.attributes?.map(attribute=><div key={attribute.label}><span>{attribute.label}</span><strong>{attribute.value}</strong></div>)}<div><span>Requirement status</span><strong>{item.mandatory===true?"Mandatory":item.mandatory===false?"Conditional":"Unspecified"}</strong></div><div><span>Review status</span><strong>{state==="needs-review"?"Needs Review":state==="reviewed"?"Reviewed":"Ready"}</strong></div>{item.evidenceExpected?.length?<div><span>Expected evidence</span><strong>{item.evidenceExpected.join(" · ")}</strong></div>:null}</section></div></div></section>}
function ConfirmDialog({unresolved,onClose,onReview,onConfirm}:{unresolved:number;onClose:()=>void;onReview:()=>void;onConfirm:()=>void}){return <div className={styles.overlay}><button className={styles.backdrop} aria-label="Close confirmation" onClick={onClose}/><section className={styles.dialog} role="alertdialog" aria-modal="true" aria-labelledby="confirm-title"><div className={styles.dialogIcon}><LockIcon/></div><small>Evaluation specification</small><h2 id="confirm-title">Confirm Tender Blueprint</h2><p>{unresolved?`${unresolved} interpretations still require acknowledgement. You can continue reviewing or confirm while preserving their review flags.`:"All requirements are ready. Confirm this Blueprint as the shared specification for vendor evaluation."}</p><div className={styles.dialogActions}><button className={styles.secondaryButton} onClick={onReview}>Continue Reviewing</button><button className="button" onClick={onConfirm}>{unresolved?"Confirm with Review Flags":"Confirm Blueprint"}</button></div></section></div>}
function Processing({step}:{step:number}){const completed=Math.min(3,Math.floor(step*4/(processingMessages.length-1)));return <div className={styles.processing}><div className={styles.processingCard}><div className={styles.processingMark}><DocumentIcon/><i/></div><span>Preparing Tender Blueprint</span><h1>{processingMessages[step]}</h1><p>Structuring the local preview into a review-ready procurement specification.</p><div className={styles.processRail}>{processingSteps.map((label,index)=><div className={`${styles.processStep} ${index<=completed?styles.processComplete:""}`} key={label}><i>{index<completed?<CheckIcon/>:index+1}</i><strong>{label}</strong></div>)}</div><div className={styles.progress}><i style={{width:`${(step+1)*20}%`}}/></div><small>Preview processing · no external service is being called</small></div></div>}
function StatePanel({title,copy,action,onAction,kind}:{title:string;copy:string;action?:string;onAction:()=>void;kind?:"loading"}){return <div className={styles.statePanel}><div className={kind?styles.skeletonMark:styles.stateMark}><DocumentIcon/></div><p>Tender Blueprint</p><h1>{title}</h1><span>{copy}</span>{kind?<div className={styles.skeletonLines}><i/><i/><i/></div>:<button className="button" onClick={onAction}>{action}</button>}<Link href="/organization/tenders" className={styles.backLink}>Return to Tenders</Link></div>}

function SearchIcon(){return <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="6"/><path d="m16 16 4 4"/></svg>}
function ArrowIcon(){return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14M14 7l5 5-5 5"/></svg>}
function CheckIcon(){return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12 4 4L19 6"/></svg>}
function LockIcon(){return <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/></svg>}
function DocumentIcon(){return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 3h8l4 4v14H6z"/><path d="M14 3v5h4M9 12h6M9 16h6"/></svg>}
