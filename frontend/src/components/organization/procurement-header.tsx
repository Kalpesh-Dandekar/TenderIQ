import type { ReactNode } from "react";
import styles from "./procurement.module.css";
export function ProcurementHeader({ context, title, description, action }: { context: string; title: string; description: string; action?: ReactNode }) { return <header className={styles.header}><div><p className={styles.kicker}>{context}</p><h1>{title}</h1><p>{description}</p></div>{action}</header>; }
