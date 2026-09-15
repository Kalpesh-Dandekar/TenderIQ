import { Router } from "express";

export const apiRouter = Router();

apiRouter.get("/", (_request, response) => {
  response.status(200).json({ success: true, service: "TenderIQ API" });
});
