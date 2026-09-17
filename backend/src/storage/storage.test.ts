import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { AppError } from "../errors/app-error.js";
import { sha256, validatePdf } from "../documents/pdf.js";
import { LocalStorageProvider } from "./local-storage-provider.js";
import { StorageError } from "./storage-provider.js";

const pdf = Buffer.from("%PDF-1.7\nTenderIQ test PDF");
void test("PDF validation and SHA-256 are deterministic", () => { validatePdf({ originalFilename:"tender.PDF", mimeType:"application/pdf", data:pdf, maxSizeBytes:1024 }); assert.equal(sha256(pdf), sha256(Buffer.from(pdf))); assert.match(sha256(pdf), /^[a-f0-9]{64}$/); });
for (const [name,input,code] of [
  ["invalid extension",{originalFilename:"x.txt",mimeType:"application/pdf",data:pdf,maxSizeBytes:1024},"INVALID_DOCUMENT_EXTENSION"],
  ["invalid header",{originalFilename:"x.pdf",mimeType:"application/pdf",data:Buffer.from("not pdf"),maxSizeBytes:1024},"INVALID_PDF"],
  ["empty file",{originalFilename:"x.pdf",mimeType:"application/pdf",data:Buffer.alloc(0),maxSizeBytes:1024},"EMPTY_DOCUMENT"],
  ["oversized file",{originalFilename:"x.pdf",mimeType:"application/pdf",data:pdf,maxSizeBytes:2},"DOCUMENT_TOO_LARGE"],
] as const) void test(`rejects ${name}`,()=>assert.throws(()=>validatePdf(input),(error:unknown)=>error instanceof AppError&&error.code===code));
void test("local provider stores immutable objects and rejects traversal",async()=>{const root=await mkdtemp(join(tmpdir(),"tenderiq-storage-"));try{const provider=new LocalStorageProvider(root),key="tenders/t1/documents/d1/v1.pdf";await provider.put({key,data:pdf});assert.equal(await provider.exists(key),true);assert.deepEqual((await provider.get(key)).data,pdf);await assert.rejects(()=>provider.put({key,data:pdf}),(error:unknown)=>error instanceof StorageError&&error.code==="ALREADY_EXISTS");await assert.rejects(()=>provider.get("../outside.pdf"),(error:unknown)=>error instanceof StorageError&&error.code==="INVALID_KEY");await provider.delete(key);assert.equal(await provider.exists(key),false);await provider.delete(key);}finally{await rm(root,{recursive:true,force:true})}});
