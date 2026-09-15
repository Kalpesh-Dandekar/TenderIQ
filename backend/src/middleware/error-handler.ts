import type { ErrorRequestHandler } from "express";

export const errorHandler: ErrorRequestHandler = (error: unknown, _request, response, next) => {
  void next;
  console.error(error);
  response.status(500).json({ success: false, error: "Internal Server Error" });
};
