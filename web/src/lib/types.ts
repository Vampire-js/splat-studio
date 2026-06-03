/**
 * Shared API contracts between the Next.js app and the FastAPI worker.
 * Keep in sync with worker/app/models.py.
 */

export type JobStatus = 'queued' | 'processing' | 'done' | 'failed';

export interface Job {
  id: string;
  status: JobStatus;
  /** ISO-8601 timestamp. */
  created_at: string;
  /** 0..1 */
  progress: number;
  image_count: number;
  /** Worker-relative URL once status === 'done'. */
  splat_url?: string | null;
  error?: string | null;
}

export interface CreateJobResponse {
  id: string;
}
