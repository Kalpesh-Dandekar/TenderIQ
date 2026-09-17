import { resolve } from "node:path";
import { env } from "../config/env.js";
import { LocalStorageProvider } from "./local-storage-provider.js";
import type { StorageProvider } from "./storage-provider.js";

export function createStorageProvider(): StorageProvider {
  if (env.STORAGE_PROVIDER === "local") return new LocalStorageProvider(resolve(process.cwd(), env.LOCAL_STORAGE_PATH));
  throw new Error(`Unsupported storage provider: ${String(env.STORAGE_PROVIDER)}`);
}

export const storageProvider = createStorageProvider();
