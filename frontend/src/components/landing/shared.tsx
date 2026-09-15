import type { ReactNode } from "react";

export function Eyebrow({ children }: { children: ReactNode }) { return <p className="eyebrow"><span />{children}</p>; }
export function SectionHeading({ eyebrow, title, copy }: { eyebrow: string; title: ReactNode; copy?: string }) { return <div className="section-heading"><Eyebrow>{eyebrow}</Eyebrow><h2>{title}</h2>{copy ? <p>{copy}</p> : null}</div>; }
export function ArrowIcon() { return <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 8h9M8.5 4.5 12 8l-3.5 3.5" /></svg>; }
export function CheckIcon() { return <svg viewBox="0 0 16 16" aria-hidden="true"><path d="m3.5 8 3 3 6-6" /></svg>; }
