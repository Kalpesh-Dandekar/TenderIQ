import { randomUUID } from "node:crypto";
import { StorageError } from "./storage-provider.js";

const SAFE_SEGMENT = /^[A-Za-z0-9._-]+$/;

export function validateStorageKey(key: string): string {
  if (!key || key.startsWith("/") || key.includes("\\")) throw new StorageError("INVALID_KEY", "Invalid storage key");
  const segments = key.split("/");
  if (segments.some((segment) => !segment || segment === "." || segment === ".." || !SAFE_SEGMENT.test(segment))) throw new StorageError("INVALID_KEY", "Invalid storage key");
  return segments.join("/");
}

export function tenderDocumentKey(tenderId: string, documentId: string, version: number): string {
  return validateStorageKey(`tenders/${tenderId}/documents/${documentId}/v${version}.pdf`);
}

export function vendorDocumentVersionKey(vendorId: string, vendorDocumentId: string, version: number): string {
  return validateStorageKey(`vendors/${vendorId}/documents/${vendorDocumentId}/versions/${version}/${randomUUID()}.pdf`);
}
