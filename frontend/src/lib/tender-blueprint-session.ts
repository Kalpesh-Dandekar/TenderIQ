import type { BackendBlueprintResponse } from "./tender-blueprint-contract";

const SESSION_KEY = "tenderiq.backend-blueprint";

export function storeBackendBlueprint(value: BackendBlueprintResponse): void {
  window.sessionStorage.setItem(SESSION_KEY, JSON.stringify(value));
}

export function readBackendBlueprint(): BackendBlueprintResponse | null {
  const stored = window.sessionStorage.getItem(SESSION_KEY);
  if (!stored) return null;
  try {
    return JSON.parse(stored) as BackendBlueprintResponse;
  } catch {
    window.sessionStorage.removeItem(SESSION_KEY);
    return null;
  }
}
