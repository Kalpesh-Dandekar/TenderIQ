import { createHash } from "node:crypto";
import { extname } from "node:path";
import { AppError } from "../errors/app-error.js";

const PDF_HEADER = Buffer.from("%PDF-");
export function validatePdf(input: { originalFilename: string; mimeType?: string; data: Buffer; maxSizeBytes: number }): void {
  if (input.data.byteLength === 0) throw new AppError(400, "EMPTY_DOCUMENT", "Document is empty");
  if (input.data.byteLength > input.maxSizeBytes) throw new AppError(413, "DOCUMENT_TOO_LARGE", "Document exceeds configured size limit");
  if (extname(input.originalFilename).toLowerCase() !== ".pdf") throw new AppError(400, "INVALID_DOCUMENT_EXTENSION", "Only PDF files are accepted");
  if (input.mimeType && !["application/pdf", "application/x-pdf"].includes(input.mimeType.toLowerCase())) throw new AppError(400, "INVALID_DOCUMENT_MIME", "Only PDF files are accepted");
  if (input.data.byteLength < PDF_HEADER.byteLength || !input.data.subarray(0, PDF_HEADER.byteLength).equals(PDF_HEADER)) throw new AppError(400, "INVALID_PDF", "File does not contain a valid PDF header");
}
export const sha256 = (data: Uint8Array): string => createHash("sha256").update(data).digest("hex");
