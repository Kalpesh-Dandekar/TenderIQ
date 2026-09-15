import type { Server } from "node:http";
import { app } from "./app.js";
import { env } from "./config/env.js";

const server: Server = app.listen(env.PORT, () => {
  console.log(`TenderIQ API listening on port ${env.PORT}`);
});

let isShuttingDown = false;

function shutdown(signal: NodeJS.Signals): void {
  if (isShuttingDown) return;
  isShuttingDown = true;
  console.log(`${signal} received; shutting down`);
  server.close((error) => {
    if (error) {
      console.error("Graceful shutdown failed", error);
      process.exitCode = 1;
    }
  });
}

process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);
