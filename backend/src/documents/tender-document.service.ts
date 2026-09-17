import { randomUUID } from "node:crypto";
import { basename } from "node:path";
import { prisma } from "../config/prisma.js";
import { AppError } from "../errors/app-error.js";
import type { StorageProvider } from "../storage/storage-provider.js";
import { tenderDocumentKey } from "../storage/storage-keys.js";
import { sha256, validatePdf } from "./pdf.js";

export type TenderDocumentUpload = { originalFilename: string; mimeType: string; data: Buffer; maxSizeBytes: number };

export class TenderDocumentService {
  constructor(private readonly storage: StorageProvider) {}
  async upload(tenderId: string, upload: TenderDocumentUpload) {
    validatePdf(upload);
    const tender = await prisma.tender.findUnique({ where: { id: tenderId }, select: { id: true } });
    if (!tender) throw new AppError(404, "TENDER_NOT_FOUND", "Tender not found");
    const latest = await prisma.tenderDocument.aggregate({ where: { tenderId }, _max: { version: true } });
    const version = (latest._max.version ?? 0) + 1;
    const id = randomUUID();
    const storageKey = tenderDocumentKey(tenderId, id, version);
    const hash = sha256(upload.data);
    await this.storage.put({ key: storageKey, data: upload.data });
    try {
      return await prisma.tenderDocument.create({ data: { id, tenderId, originalFilename: basename(upload.originalFilename), storageKey, mimeType: "application/pdf", sizeBytes: BigInt(upload.data.byteLength), sha256: hash, version } });
    } catch (error) {
      try { await this.storage.delete(storageKey); } catch (cleanupError) { console.error("Tender document cleanup failed", cleanupError); }
      throw error;
    }
  }
  async download(tenderId: string, documentId: string) {
    const document = await prisma.tenderDocument.findFirst({ where: { id: documentId, tenderId } });
    if (!document) throw new AppError(404, "DOCUMENT_NOT_FOUND", "Tender document not found");
    const object = await this.storage.get(document.storageKey);
    return { document, data: object.data };
  }
}
