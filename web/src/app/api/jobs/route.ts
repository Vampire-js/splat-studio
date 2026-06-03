import { NextResponse } from 'next/server';
import { createJob } from '@/lib/worker-client';

export const runtime = 'nodejs'; // needs streaming multipart support

export async function POST(req: Request) {
  // We re-stream the incoming multipart body to the worker. Next.js's
  // `req.formData()` parses + buffers — fine for v0 image sets; for prod we'd
  // switch to direct-to-S3 pre-signed uploads (see lib/storage.ts).
  const form = await req.formData();
  const outbound = new FormData();
  for (const [key, value] of form.entries()) {
    if (key === 'images' && value instanceof File) {
      outbound.append('images', value, value.name);
    }
  }
  const result = await createJob(outbound);
  return NextResponse.json(result, { status: 201 });
}
