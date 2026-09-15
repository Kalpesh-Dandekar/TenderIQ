"use client";
import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { createDemoSession, DEMO_USER, validateDemoCredentials, type AccountRole } from "@/lib/demo-auth";
import { PasswordField } from "./password-field";
import { RoleToggle } from "./role-toggle";
import styles from "./auth.module.css";

export function LoginForm() {
  const router = useRouter();
  const [role, setRole] = useState<AccountRole>("organization");
  const [identifier, setIdentifier] = useState(""); const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<{ identifier?: string; password?: string }>({}); const [formError, setFormError] = useState("");
  function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const nextErrors = { identifier: identifier.trim() ? undefined : "Enter your username or email.", password: password ? undefined : "Enter your password." }; setErrors(nextErrors); setFormError(""); if (nextErrors.identifier || nextErrors.password) return; if (!validateDemoCredentials(identifier, password)) { setFormError("Invalid username/email or password."); return; } createDemoSession(role, identifier); router.push(role === "organization" ? "/organization" : "/vendor"); }
  return <div className={styles.card}><header className={styles.cardHeader}><p className={styles.micro}>Secure procurement workspace</p><h1>Welcome back.</h1><p>Select your role and enter your workspace credentials.</p></header><RoleToggle value={role} onChange={setRole} /><form className={styles.form} onSubmit={submit} noValidate>{formError ? <div className={styles.formError} role="alert">{formError}</div> : null}<div className={styles.field}><label htmlFor="identifier">Username or email</label><input className={styles.input} id="identifier" value={identifier} onChange={(event) => setIdentifier(event.target.value)} autoComplete="username" aria-invalid={Boolean(errors.identifier)} aria-describedby={errors.identifier ? "identifier-error" : undefined} placeholder="Enter username or email" />{errors.identifier ? <span className={styles.error} id="identifier-error">{errors.identifier}</span> : null}</div><PasswordField id="password" label="Password" value={password} onChange={setPassword} error={errors.password} autoComplete="current-password" /><button className={`button ${styles.submit}`} type="submit">Sign In <span aria-hidden="true">→</span></button><p className={styles.secondary}>New to TenderIQ? <a href="/register">Create account</a></p></form><div className={styles.demo}><span>Demo access</span><strong>{DEMO_USER.username} or {DEMO_USER.email} · {DEMO_USER.password}</strong></div></div>;
}
