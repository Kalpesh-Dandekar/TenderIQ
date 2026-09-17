import { mkdir, readFile, stat, unlink, writeFile } from "node:fs/promises";
import { dirname, resolve, sep } from "node:path";
import type { PutObjectInput, StorageProvider, StoredObject } from "./storage-provider.js";
import { StorageError } from "./storage-provider.js";
import { validateStorageKey } from "./storage-keys.js";

export class LocalStorageProvider implements StorageProvider {
  private readonly root: string;
  constructor(rootPath: string) { this.root = resolve(rootPath); }
  private pathFor(key: string): string { const path = resolve(this.root, ...validateStorageKey(key).split("/")); if (!path.startsWith(`${this.root}${sep}`)) throw new StorageError("INVALID_KEY", "Storage key escapes configured root"); return path; }
  async put(input: PutObjectInput) { const path = this.pathFor(input.key); try { await mkdir(dirname(path), { recursive: true }); await writeFile(path, input.data, { flag: "wx" }); return { key: input.key, sizeBytes: input.data.byteLength }; } catch (error) { if ((error as NodeJS.ErrnoException).code === "EEXIST") throw new StorageError("ALREADY_EXISTS", "Storage object already exists", { cause: error }); throw new StorageError("IO_ERROR", "Unable to store object", { cause: error }); } }
  async get(key: string): Promise<StoredObject> { const path = this.pathFor(key); try { const data = await readFile(path); return { key, data, sizeBytes: data.byteLength }; } catch (error) { if ((error as NodeJS.ErrnoException).code === "ENOENT") throw new StorageError("NOT_FOUND", "Storage object not found", { cause: error }); throw new StorageError("IO_ERROR", "Unable to read object", { cause: error }); } }
  async exists(key: string): Promise<boolean> { try { await stat(this.pathFor(key)); return true; } catch (error) { if ((error as NodeJS.ErrnoException).code === "ENOENT") return false; throw new StorageError("IO_ERROR", "Unable to inspect object", { cause: error }); } }
  async delete(key: string): Promise<void> { try { await unlink(this.pathFor(key)); } catch (error) { if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw new StorageError("IO_ERROR", "Unable to delete object", { cause: error }); } }
}
