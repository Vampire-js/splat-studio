/**
 * Server-only client for the FastAPI worker. Centralizing the base URL and
 * fetch contracts here means we can swap the worker transport (HTTP -> queue,
 * direct call, etc.) without changing API route handlers.
 */
import 'server-only';
import type { CreateJobResponse, Job } from './types';

const BASE = process.env.WORKER_BASE_URL ?? 'http://localhost:8000';

export async function createJob(form: FormData): Promise<CreateJobResponse> {
  const res = await fetch(`${BASE}/jobs`, { method: 'POST', body: form });
  if (!res.ok) throw new Error(`worker createJob failed: ${res.status} ${await res.text()}`);
  return (await res.json()) as CreateJobResponse;
}

export async function getJob(id: string): Promise<Job> {
  const res = await fetch(`${BASE}/jobs/${encodeURIComponent(id)}`, { cache: 'no-store' });
  if (res.status === 404) throw new Error('not_found');
  if (!res.ok) throw new Error(`worker getJob failed: ${res.status}`);
  return (await res.json()) as Job;
}

export async function getSplatStream(id: string): Promise<Response> {
  return fetch(`${BASE}/jobs/${encodeURIComponent(id)}/splat`, { cache: 'no-store' });
}
