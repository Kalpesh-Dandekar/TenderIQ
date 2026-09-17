import { Router } from "express";
import { tenderDocumentRouter } from "../documents/tender-document.route.js";

export const apiRouter = Router();

apiRouter.get("/", (_request, response) => {
  response.status(200).json({ success: true, service: "TenderIQ API" });
});

apiRouter.use("/tenders/:tenderId/documents", tenderDocumentRouter);
