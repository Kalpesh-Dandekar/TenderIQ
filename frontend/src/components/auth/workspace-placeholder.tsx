"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { BrandMark } from "@/components/landing/brand-mark";
import { clearDemoSession, getDemoSession, type AccountRole, type DemoSession } from "@/lib/demo-auth";
import styles from "./auth.module.css";

export function WorkspacePlaceholder({ role }: { role: AccountRole }) {
  const router = useRouter(); const [session, setSession] = useState<DemoSession | null>(null); const [checking, setChecking] = useState(true);
  useEffect(() => { const timer = window.setTimeout(() => { const current = getDemoSession(); if (!current || current.role !== role) { router.replace("/login"); return; } setSession(current); setChecking(false); }, 0); return () => window.clearTimeout(timer); }, [role, router]);
  if (checking || !session) return <main className={styles.workspace}><p className={styles.loading}>Validating demo session…</p></main>;
  const organization = role === "organization";
  return <main className={styles.workspace}><section className={styles.workspaceCard}><Link className="wordmark" href="/"><BrandMark />Tender<span className="accent-text">IQ</span></Link><h1>{organization ? "Organization" : "Vendor"} Workspace</h1><p>{organization ? "Tender creation and procurement management will be available here." : "Tender participation and proposal management will be available here."}</p><div className={styles.workspaceMeta}><span>Demo session</span><span>{organization ? "Organization" : "Vendor"}</span></div><button className="button" type="button" onClick={() => { clearDemoSession(); router.replace("/login"); }}>Sign Out</button></section></main>;
}
