import { NextResponse } from 'next/server';
import { getJob } from '@/lib/worker-client';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function GET(_req: Request, { params }: { params: { id: string } }) {
  try {
    const job = await getJob(params.id);
    return NextResponse.json(job);
  } catch (e) {
    const msg = (e as Error).message;
    if (msg === 'not_found') {
      return NextResponse.json({ error: 'not_found' }, { status: 404 });
    }
    return NextResponse.json({ error: msg }, { status: 502 });
  }
}
