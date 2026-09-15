"use client";
import { useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { BrandMark } from "@/components/landing/brand-mark";
import { clearDemoSession, getDemoSession } from "@/lib/demo-auth";
import { Icon, type IconName } from "./icons";
import styles from "./organization.module.css";

const primary = [
  { label: "Overview", href: "/organization", icon: "overview" },
  { label: "Tenders", href: "/organization/tenders", icon: "tenders" },
  { label: "Bids & Evaluation", href: "/organization/evaluation", icon: "evaluation" },
  { label: "Vendors", href: "/organization/vendors", icon: "vendors" },
  { label: "Procurement Insights", href: "/organization/insights", icon: "insights" },
  { label: "Procurement Delivery", href: "/organization/delivery", icon: "delivery" },
] as const satisfies ReadonlyArray<{ label: string; href: string; icon: IconName }>;

const secondary = [
  { label: "Settings", href: "/organization/settings", icon: "settings" },
  { label: "Organization Profile", href: "/organization/profile", icon: "profile" },
] as const satisfies ReadonlyArray<{ label: string; href: string; icon: IconName }>;

export function OrganizationShell({ children }: { children: ReactNode }) {
  const pathname = usePathname(); const router = useRouter(); const [drawer, setDrawer] = useState(false); const [ready, setReady] = useState(false);
  useEffect(() => { const timer = window.setTimeout(() => { const session = getDemoSession(); if (!session || session.role !== "organization") { router.replace("/login"); return; } setReady(true); }, 0); return () => window.clearTimeout(timer); }, [router]);
  useEffect(() => { if (!drawer) return; const close = (event: KeyboardEvent) => { if (event.key === "Escape") setDrawer(false); }; document.addEventListener("keydown", close); document.body.style.overflow = "hidden"; return () => { document.removeEventListener("keydown", close); document.body.style.overflow = ""; }; }, [drawer]);
  if (!ready) return <main className={styles.placeholder}><p className={styles.placeholderMeta}>Validating organization workspace…</p></main>;
  const context = primary.find((item) => item.href === "/organization" ? pathname === item.href : pathname.startsWith(item.href))?.label ?? secondary.find((item) => pathname.startsWith(item.href))?.label ?? "Organization";
  const logout = () => { clearDemoSession(); router.replace("/login"); };
  return <div className={styles.shell}>{drawer ? <button className={styles.backdrop} aria-label="Close navigation" onClick={() => setDrawer(false)} /> : null}<aside className={`${styles.sidebar} ${drawer ? styles.open : ""}`} aria-label="Organization navigation"><div className={styles.brand}><Link className="wordmark" href="/"><BrandMark /><span>Tender<span className="accent-text">IQ</span></span></Link></div><span className={styles.navLabel}>Organization workspace</span><nav className={styles.nav}>{primary.map((item) => <NavItem key={item.href} {...item} pathname={pathname} onNavigate={() => setDrawer(false)} />)}</nav><div className={styles.sidebarBottom}>{secondary.map((item) => <NavItem key={item.href} {...item} pathname={pathname} bottom onNavigate={() => setDrawer(false)} />)}<button className={`${styles.bottomButton} ${styles.logout}`} type="button" onClick={logout}><Icon name="logout" />Logout</button></div></aside><div className={styles.main}><header className={styles.topbar}><div className={styles.pageContext}><button className={styles.menuButton} type="button" aria-label="Open navigation" aria-expanded={drawer} onClick={() => setDrawer(true)}><Icon name="menu" /></button><i /><span>Organization</span><span>/</span><b>{context}</b></div><button className={styles.menuButton} type="button" aria-label="Open navigation" aria-expanded={drawer} onClick={() => setDrawer(true)}><Icon name="menu" /></button><div className={styles.topActions}><button className={styles.search} type="button" aria-label="Open global search"><Icon name="search" /><span>Search tenders, vendors, proposals</span><kbd>⌘ K</kbd></button><button className={styles.iconButton} type="button" aria-label="Notifications"><Icon name="bell" /><i className={styles.noticeDot} /></button><Link className={styles.account} href="/organization/profile"><i className={styles.accountMark}>OR</i><span>Organization</span></Link></div></header><main className={styles.content}>{children}</main></div></div>;
}

function NavItem({ label, href, icon, pathname, bottom = false, onNavigate }: { label: string; href: string; icon: IconName; pathname: string; bottom?: boolean; onNavigate: () => void }) {
  const active = href === "/organization" ? pathname === href : pathname.startsWith(href);
  return <Link href={href} onClick={onNavigate} className={bottom ? styles.bottomButton : `${styles.navLink} ${active ? styles.active : ""}`} aria-current={active ? "page" : undefined}><Icon name={icon} />{label}</Link>;
}
