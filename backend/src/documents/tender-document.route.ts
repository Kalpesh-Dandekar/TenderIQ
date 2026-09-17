import { Router } from "express";
import multer from "multer";
import { env } from "../config/env.js";
import { AppError } from "../errors/app-error.js";
import { storageProvider } from "../storage/index.js";
import { TenderDocumentService } from "./tender-document.service.js";

const maxSizeBytes = Math.floor(env.MAX_DOCUMENT_SIZE_MB * 1024 * 1024);
const upload = multer({ storage: multer.memoryStorage(), limits: { fileSize: maxSizeBytes, files: 1 } });
const service = new TenderDocumentService(storageProvider);
export const tenderDocumentRouter = Router({ mergeParams: true });

tenderDocumentRouter.post("/", upload.single("file"), async (request, response) => {
  if (!request.file) throw new AppError(400, "DOCUMENT_REQUIRED", "Multipart field 'file' is required");
  const document = await service.upload(routeParam(request.params["tenderId"]), { originalFilename: request.file.originalname, mimeType: request.file.mimetype, data: request.file.buffer, maxSizeBytes });
  response.status(201).json({ success: true, document: serialize(document) });
});

tenderDocumentRouter.get("/:documentId/download", async (request, response) => {
  const params = request.params as Record<string, string | string[] | undefined>;
  const result = await service.download(routeParam(params["tenderId"]), routeParam(params["documentId"]));
  const safeName = result.document.originalFilename.replace(/["\r\n]/g, "_");
  response.setHeader("Content-Type", "application/pdf");
  response.setHeader("Content-Disposition", `attachment; filename="${safeName}"`);
  response.setHeader("Content-Length", String(result.data.byteLength));
  response.send(result.data);
});

function serialize(document: { id:string; tenderId:string; originalFilename:string; mimeType:string; sizeBytes:bigint; sha256:string; version:number; createdAt:Date }) {
  return { ...document, sizeBytes: Number(document.sizeBytes) };
}

function routeParam(value: string | string[] | undefined): string {
  if (typeof value !== "string" || !value) throw new AppError(400, "INVALID_ROUTE_PARAMETER", "Invalid route parameter");
  return value;
}
