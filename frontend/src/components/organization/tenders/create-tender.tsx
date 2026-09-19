"use client";
import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { generateTenderBlueprint } from "@/lib/tender-blueprint-api";
import { storeBackendBlueprint } from "@/lib/tender-blueprint-session";
import { ProcurementHeader } from "../procurement-header";
import styles from "../procurement.module.css";

type Method = "ai" | "manual" | "upload";

export function CreateTender() {
  const [method,setMethod]=useState<Method>("upload");
  return <div className={styles.page}><ProcurementHeader context="Procurement intake" title="Create Tender" description="Choose the workflow that matches the procurement source and level of structure available."/><div className={styles.methodGrid}><MethodButton id="ai" number="01" title="Create with AI" copy="Describe the procurement requirement and prepare a structured tender draft for review." active={method==="ai"} onClick={setMethod}/><MethodButton id="manual" number="02" title="Create Manually" copy="Build the tender using structured procurement sections and templates." active={method==="manual"} onClick={setMethod}/><MethodButton id="upload" number="03 · Document ingest" title="Upload Existing Tender" copy="Convert an existing procurement document into a structured Tender Blueprint." active={method==="upload"} emphasis onClick={setMethod}/></div>{method==="ai"?<AiFlow/>:method==="manual"?<ManualFlow/>:<UploadFlow/>}</div>;
}

function MethodButton({id,number,title,copy,active,emphasis,onClick}:{id:Method;number:string;title:string;copy:string;active:boolean;emphasis?:boolean;onClick:(id:Method)=>void}) {
  return <button className={`${styles.method} ${active?styles.methodActive:""} ${emphasis?styles.methodEmphasis:""}`} type="button" onClick={()=>onClick(id)}><small>{number}</small><h2>{title}</h2><p>{copy}</p><b>{active?"Selected":"Choose workflow"} →</b></button>;
}

function AiFlow() {
  const [ready,setReady]=useState(false);
  return <section className={styles.flowPanel}><h2>AI-Assisted Tender Brief</h2><form className={styles.formGrid} onSubmit={event=>{event.preventDefault();setReady(true)}}><Field label="Procurement Title"/><Field label="Category"/><div className={`${styles.field} ${styles.fieldWide}`}><label>Short Procurement Need / Scope</label><textarea className={styles.textarea} required/></div><Field label="Estimated Budget"/><Field label="Expected Completion / Delivery Period"/><button className="button" type="submit">Prepare Draft</button></form>{ready?<p className={styles.integration}>Integration-ready: draft preparation will begin when TenderIQ intelligence services are connected. No draft has been generated.</p>:null}</section>;
}

function ManualFlow() {
  return <section className={styles.flowPanel}><h2>Structured Tender Form</h2><div className={styles.tabs}>{["Basic Details","Scope","Eligibility","Financial Requirements","Required Documents","Timeline"].map(item=><span className={styles.tab} key={item}>{item}</span>)}</div><form className={styles.formGrid}><Field label="Tender Title"/><Field label="Tender Reference"/><div className={`${styles.field} ${styles.fieldWide}`}><label>Scope Summary</label><textarea className={styles.textarea}/></div><Field label="Estimated Cost"/><Field label="Submission Deadline"/><button className="button" type="button">Save Structured Draft</button></form></section>;
}

function UploadFlow() {
  const router=useRouter(); const [file,setFile]=useState<File|null>(null); const [preview,setPreview]=useState(false); const [demo,setDemo]=useState(false); const [analyzing,setAnalyzing]=useState(false); const [error,setError]=useState<string|null>(null);
  function submit(event:FormEvent){event.preventDefault();if(file||demo)setPreview(true)}
  async function analyze(){
    if(demo){router.push("/organization/tenders/it-software-rfp/blueprint?source=preview&state=processing");return}
    if(!file)return;
    setAnalyzing(true);setError(null);
    try{const response=await generateTenderBlueprint(file);storeBackendBlueprint(response);router.push("/organization/tenders/it-software-rfp/blueprint?source=backend")}
    catch(cause){setError(cause instanceof Error?cause.message:"Tender Blueprint generation failed");setAnalyzing(false)}
  }
  return <section className={styles.flowPanel}><h2>Existing Tender Document</h2><form className={styles.formGrid} onSubmit={submit}><div className={`${styles.drop} ${styles.fieldWide}`}><strong>Drop a tender PDF here</strong><p>PDF only · selected locally · nothing is uploaded until analysis is requested</p><input type="file" accept="application/pdf,.pdf" aria-label="Choose tender PDF" onChange={event=>{setFile(event.target.files?.[0]??null);setDemo(false);setPreview(false);setError(null)}}/>{file?<div className={styles.selectedFile}><span>{file.name} · {(file.size/1024/1024).toFixed(2)} MB</span><button type="button" className={styles.action} onClick={()=>{setFile(null);setPreview(false)}}>Remove</button></div>:null}</div><Field label="Tender Title" value={demo?"IT Software RFP":undefined}/><Field label="Tender Reference" value={demo?"IIITB/IT/RFP/2026":undefined}/><Field label="Procurement Category" value={demo?"Information Technology":undefined}/><Field label="Organization" value={demo?"IIIT Bangalore":undefined}/><div className={styles.actions}><button className="button button--ghost" type="button" onClick={()=>{setDemo(true);setFile(null);setPreview(false);setError(null)}}>Load Blueprint Preview</button><button className="button" type="submit">Continue to Preview</button></div></form>{preview?<div className={styles.pipeline}>{["Document Ingest","Text Extraction","Section Detection","Requirement Extraction","Blueprint Generation"].map((item,index)=><div className={styles.pipelineStep} key={item}><small>0{index+1}</small><strong>{item}</strong></div>)}</div>:null}{preview?<div className={styles.integration}>{demo?"Deterministic preview data will be used. No external analysis will occur.":"The selected PDF will be sent to the configured Tender Blueprint service when analysis starts."} <button className={styles.action} type="button" disabled={analyzing} onClick={analyze}>{analyzing?"Analyzing…":"Analyze Tender →"}</button>{error?<p role="alert">{error}</p>:null}</div>:null}</section>;
}

function Field({label,value}:{label:string;value?:string}) {
  return <div className={styles.field}><label>{label}</label><input className={styles.input} defaultValue={value} required/></div>;
}
