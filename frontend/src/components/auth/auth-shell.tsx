import type { ReactNode } from "react";
import Link from "next/link";
import { BrandMark } from "@/components/landing/brand-mark";
import styles from "./auth.module.css";

export function AuthShell({ children, mode }: { children: ReactNode; mode: "login" | "register" }) {
  return <main className={styles.shell}><aside className={styles.context}><div className={styles.contextTop}><Link className="wordmark" href="/"><BrandMark /><span>Tender<span className="accent-text">IQ</span></span></Link><Link className={styles.back} href="/">← Home</Link></div><div className={styles.contextCopy}><p className={styles.micro}>Procurement intelligence</p><h2>{mode === "login" ? <>A secure path to <span>defensible decisions.</span></> : <>One identity across the <span>evidence chain.</span></>}</h2><p>Enter a workspace where requirements, evidence, evaluation, and procurement decisions remain connected.</p></div><AuthContextVisual /><div className={styles.contextFoot}><span>Evidence grounded</span><span>Traceable by design</span></div></aside><section className={styles.panel}>{children}</section></main>;
}

function AuthContextVisual() {
  return <div className={styles.systemVisual} aria-label="Requirement, evidence, and validation relationship"><div className={styles.systemBar}><span><i /> TRUST CHAIN</span><span>TIQ / AUTH</span></div><div className={styles.systemFlow}><Node label="Input" title="Requirement" meta="Structured" /><i className={styles.connector} /><Node label="Source" title="Evidence" meta="Linked" /><i className={styles.connector} /><Node label="Outcome" title="Decision" meta="Traceable" /></div></div>;
}
function Node({ label, title, meta }: { label: string; title: string; meta: string }) { return <div className={styles.systemNode}><small>{label}</small><strong>{title}</strong><span>{meta}</span></div>; }
