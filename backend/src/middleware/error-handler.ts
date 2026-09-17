import type { ErrorRequestHandler } from "express";
import multer from "multer";
import { AppError } from "../errors/app-error.js";
import { StorageError } from "../storage/storage-provider.js";

export const errorHandler: ErrorRequestHandler = (error: unknown, _request, response, next) => {
  void next;
  if (error instanceof AppError) { response.status(error.statusCode).json({ success: false, error: error.code, message: error.message }); return; }
  if (error instanceof multer.MulterError) { const status = error.code === "LIMIT_FILE_SIZE" ? 413 : 400; response.status(status).json({ success: false, error: error.code, message: "Invalid multipart upload" }); return; }
  if (error instanceof StorageError && error.code === "NOT_FOUND") { response.status(404).json({ success: false, error: "STORED_OBJECT_NOT_FOUND", message: "Stored document is unavailable" }); return; }
  console.error(error);
  response.status(500).json({ success: false, error: "Internal Server Error" });
};
