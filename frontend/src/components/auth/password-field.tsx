"use client";
import { useState } from "react";
import styles from "./auth.module.css";

type Props = { id: string; label: string; value: string; onChange: (value: string) => void; error?: string; hint?: string; autoComplete: string };
export function PasswordField({ id, label, value, onChange, error, hint, autoComplete }: Props) {
  const [visible, setVisible] = useState(false);
  const descriptionId = error ? `${id}-error` : hint ? `${id}-hint` : undefined;
  return <div className={styles.field}><label htmlFor={id}>{label}</label><div className={styles.inputWrap}><input className={`${styles.input} ${styles.passwordInput}`} id={id} type={visible ? "text" : "password"} value={value} onChange={(event) => onChange(event.target.value)} autoComplete={autoComplete} aria-invalid={Boolean(error)} aria-describedby={descriptionId} /><button className={styles.visibility} type="button" onClick={() => setVisible((current) => !current)} aria-label={`${visible ? "Hide" : "Show"} ${label.toLowerCase()}`}>{visible ? "Hide" : "Show"}</button></div>{error ? <span className={styles.error} id={`${id}-error`}>{error}</span> : hint ? <span className={styles.hint} id={`${id}-hint`}>{hint}</span> : null}</div>;
}
