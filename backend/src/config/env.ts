import "dotenv/config";
import { z } from "zod";

const environmentSchema = z.object({
  NODE_ENV: z.enum(["development", "test", "production"]).default("development"),
  PORT: z.coerce.number().int().positive().max(65535).default(5000),
  CORS_ORIGIN: z.string().url().default("http://localhost:3000"),
  DATABASE_URL: z.string().min(1),
  STORAGE_PROVIDER: z.enum(["local"]).default("local"),
  LOCAL_STORAGE_PATH: z.string().min(1).default("./storage"),
  MAX_DOCUMENT_SIZE_MB: z.coerce.number().positive().max(100).default(25),
});

const parsedEnvironment = environmentSchema.safeParse(process.env);

if (!parsedEnvironment.success) {
  console.error("Invalid environment configuration", parsedEnvironment.error.flatten().fieldErrors);
  throw new Error("Invalid environment configuration");
}

export const env = parsedEnvironment.data;
