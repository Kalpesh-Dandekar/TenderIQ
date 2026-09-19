import type { BackendBlueprintResponse } from "./tender-blueprint-contract";

export class TenderBlueprintApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = "TenderBlueprintApiError";
  }
}

export async function generateTenderBlueprint(file: File, signal?: AbortSignal): Promise<BackendBlueprintResponse> {
  const body = new FormData();
  body.set("file", file);
  const response = await fetch("/api/tender-blueprint?mode=HYBRID", { method: "POST", body, signal });
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = isRecord(payload) && typeof payload.detail === "string" ? payload.detail : "Tender Blueprint generation failed";
    throw new TenderBlueprintApiError(detail, response.status);
  }
  if (!isBackendBlueprintResponse(payload)) throw new TenderBlueprintApiError("The Blueprint service returned an invalid response", 502);
  return payload;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isBackendBlueprintResponse(value: unknown): value is BackendBlueprintResponse {
  if (!isRecord(value) || value.success !== true || !isRecord(value.blueprint)) return false;
  const blueprint = value.blueprint;
  return typeof blueprint.source_filename === "string" && typeof blueprint.source_sha256 === "string" &&
    isRecord(blueprint.metadata) && Array.isArray(blueprint.requirements) && Array.isArray(blueprint.evaluation_stages);
}
