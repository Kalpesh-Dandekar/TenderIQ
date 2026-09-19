import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";

export async function POST(request: NextRequest) {
  const serviceUrl = process.env.AI_SERVICE_URL;
  if (!serviceUrl) return NextResponse.json({ detail: "Tender Blueprint service is not configured" }, { status: 503 });

  const incoming = await request.formData();
  const file = incoming.get("file");
  if (!(file instanceof File) || file.type !== "application/pdf") {
    return NextResponse.json({ detail: "A PDF file is required" }, { status: 400 });
  }

  const mode = request.nextUrl.searchParams.get("mode") === "FULL_LLM" ? "FULL_LLM" : "HYBRID";
  const body = new FormData();
  body.set("file", file, file.name);
  try {
    const upstream = await fetch(`${serviceUrl.replace(/\/$/, "")}/blueprint/tender?mode=${mode}`, {
      method: "POST", body, cache: "no-store",
    });
    const payload: unknown = await upstream.json().catch(() => null);
    if (!upstream.ok) return NextResponse.json({ detail: safeErrorMessage(upstream.status, payload) }, { status: upstream.status });
    return NextResponse.json(payload, { status: upstream.status });
  } catch {
    return NextResponse.json({ detail: "Tender Blueprint service is unavailable" }, { status: 503 });
  }
}

function safeErrorMessage(status: number, payload: unknown): string {
  if (status === 401) return "Authentication is required";
  if (status === 403) return "You are not authorized to generate this Blueprint";
  if (status === 404) return "Tender Blueprint service was not found";
  if (status === 413) return "The PDF exceeds the supported size limit";
  if (status === 415) return "Only PDF documents are supported";
  if (status === 400 && typeof payload === "object" && payload !== null && "detail" in payload && typeof payload.detail === "string") return payload.detail;
  return status >= 500 ? "Tender Blueprint generation failed" : "The Blueprint request could not be completed";
}
