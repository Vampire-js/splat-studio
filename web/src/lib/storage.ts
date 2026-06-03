/**
 * Storage interface stub for the Next.js side.
 *
 * v0: we don't actually persist anything on the web side — all uploaded files
 * flow straight through to the worker, which owns the filesystem. This file
 * exists so that when we move to S3 we have a clear seam: the Next.js app will
 * issue pre-signed URLs and the worker will read from S3 instead.
 *
 * TODO(storage): implement S3PresignedStorage that returns upload URLs the
 * browser POSTs to directly, and a signed GET URL for the splat artifact.
 */

export interface UploadDescriptor {
  /** Where the browser should PUT/POST the file. */
  uploadUrl: string;
  /** Stable key the worker uses to read it back. */
  objectKey: string;
}

export interface Storage {
  presignUpload(jobId: string, filename: string, contentType: string): Promise<UploadDescriptor>;
  publicSplatUrl(jobId: string): string;
}

/** v0 placeholder — not used at runtime; documents the future API surface. */
export const stubStorage: Storage = {
  async presignUpload() {
    throw new Error('Storage not implemented in v0 — uploads go through /api/jobs.');
  },
  publicSplatUrl(jobId: string) {
    return `/api/jobs/${encodeURIComponent(jobId)}/splat`;
  },
};
