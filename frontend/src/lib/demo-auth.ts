// TEMPORARY FRONTEND DEMO AUTH — replace with backend JWT/RBAC integration.
export type AccountRole = "organization" | "vendor";

export const DEMO_USER = Object.freeze({
  username: "root",
  email: "root@gmail.com",
  password: "root123456",
});

export type DemoSession = {
  authenticated: true;
  role: AccountRole;
  identifier: string;
};

const SESSION_KEY = "tenderiq.demo-session";

export function validateDemoCredentials(identifier: string, password: string): boolean {
  const normalizedIdentifier = identifier.trim().toLowerCase();
  return (
    (normalizedIdentifier === DEMO_USER.username || normalizedIdentifier === DEMO_USER.email) &&
    password === DEMO_USER.password
  );
}

export function createDemoSession(role: AccountRole, identifier: string): DemoSession {
  const session: DemoSession = { authenticated: true, role, identifier: identifier.trim().toLowerCase() };
  window.sessionStorage.setItem(SESSION_KEY, JSON.stringify(session));
  return session;
}

export function getDemoSession(): DemoSession | null {
  const stored = window.sessionStorage.getItem(SESSION_KEY);
  if (!stored) return null;
  try {
    const session: unknown = JSON.parse(stored);
    if (
      typeof session === "object" && session !== null &&
      "authenticated" in session && session.authenticated === true &&
      "role" in session && (session.role === "organization" || session.role === "vendor") &&
      "identifier" in session && typeof session.identifier === "string"
    ) return session as DemoSession;
  } catch {
    // Invalid prototype session data is treated as signed out.
  }
  clearDemoSession();
  return null;
}

export function clearDemoSession(): void {
  window.sessionStorage.removeItem(SESSION_KEY);
}
