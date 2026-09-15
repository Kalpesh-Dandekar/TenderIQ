import type { AccountRole } from "@/lib/demo-auth";
import styles from "./auth.module.css";

export function RoleToggle({ value, onChange }: { value: AccountRole; onChange: (role: AccountRole) => void }) {
  return <div className={styles.roleGroup}><span className={styles.controlLabel} id="role-label">Workspace role</span><div className={styles.roleToggle} role="radiogroup" aria-labelledby="role-label">{(["organization", "vendor"] as const).map((role) => <button key={role} type="button" role="radio" aria-checked={value === role} className={`${styles.roleButton} ${value === role ? styles.roleActive : ""}`} onClick={() => onChange(role)}>{role === "organization" ? "Organization" : "Vendor"}</button>)}</div></div>;
}
