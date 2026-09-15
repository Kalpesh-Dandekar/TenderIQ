"use client";
import { useState } from "react";
import { BrandMark } from "./brand-mark";

const links = [["Platform", "#platform"], ["How It Works", "#workflow"], ["Intelligence", "#intelligence"]] as const;
export function Navbar() {
  const [open, setOpen] = useState(false);
  return <header className="nav-wrap"><nav className="nav container" aria-label="Main navigation"><a className="wordmark" href="#top" aria-label="TenderIQ home"><BrandMark /><span>Tender<span className="accent-text">IQ</span></span></a><button className="nav-toggle" type="button" aria-label="Toggle navigation" aria-expanded={open} onClick={() => setOpen((value) => !value)}><span /><span /></button><div className={`nav-panel ${open ? "is-open" : ""}`}><div className="nav-links">{links.map(([label, href]) => <a key={href} href={href} onClick={() => setOpen(false)}>{label}</a>)}</div><div className="nav-actions"><a className="text-link" href="/login">Sign In</a><a className="button button--small" href="/register">Get Started <span aria-hidden="true">↗</span></a></div></div></nav></header>;
}
