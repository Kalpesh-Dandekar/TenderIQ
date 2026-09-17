export type StoredObject = { key: string; data: Buffer; sizeBytes: number };
export type PutObjectInput = { key: string; data: Uint8Array };

export interface StorageProvider {
  put(input: PutObjectInput): Promise<{ key: string; sizeBytes: number }>;
  get(key: string): Promise<StoredObject>;
  exists(key: string): Promise<boolean>;
  delete(key: string): Promise<void>;
}

export class StorageError extends Error {
  constructor(public readonly code: "INVALID_KEY" | "NOT_FOUND" | "ALREADY_EXISTS" | "IO_ERROR", message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "StorageError";
  }
}
