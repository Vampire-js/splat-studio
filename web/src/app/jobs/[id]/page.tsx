'use client';

import dynamic from 'next/dynamic';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import EmbedSnippet from '@/components/EmbedSnippet';
import type { Job } from '@/lib/types';

const SplatViewer = dynamic(() => import('@/components/SplatViewer'), { ssr: false });

export default function JobPage({ params }: { params: { id: string } }) {
  const { id } = params;
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let stop = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const tick = async () => {
      try {
        const res = await fetch(`/api/jobs/${id}`, { cache: 'no-store' });
        if (!res.ok) throw new Error(`status ${res.status}`);
        const data: Job = await res.json();
        if (stop) return;
        setJob(data);
        if (data.status !== 'done' && data.status !== 'failed') {
          timer = setTimeout(tick, 1000);
        }
      } catch (e) {
        if (!stop) setError((e as Error).message);
      }
    };
    tick();

    return () => {
      stop = true;
      if (timer) clearTimeout(timer);
    };
  }, [id]);

  const base = process.env.NEXT_PUBLIC_BASE_URL ?? '';
  const embedSrc = `${base}/embed/${id}`;

  return (
    <main>
      <p>
        <Link href="/">← New splat</Link>
      </p>
      <h1>Job {id}</h1>

      {error && <p style={{ color: '#f85149' }}>Error: {error}</p>}
      {!job && !error && <p>Loading…</p>}

      {job && job.status !== 'done' && job.status !== 'failed' && (
        <div>
          <p>
            Status: <strong>{job.status}</strong>
            {' — '}
            {Math.round(job.progress * 100)}%
          </p>
          <div
            style={{
              height: 8,
              background: '#21262d',
              borderRadius: 4,
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                width: `${Math.round(job.progress * 100)}%`,
                height: '100%',
                background: '#58a6ff',
                transition: 'width 0.4s ease',
              }}
            />
          </div>
          <p style={{ opacity: 0.7, fontSize: 13, marginTop: 12 }}>
            v0 stub: real pipeline (COLMAP → 3DGS training → compression) will plug in here.
          </p>
        </div>
      )}

      {job?.status === 'failed' && (
        <p style={{ color: '#f85149' }}>Job failed: {job.error}</p>
      )}

      {job?.status === 'done' && (
        <>
          <div style={{ height: 540, marginTop: 16, borderRadius: 12, overflow: 'hidden' }}>
            <SplatViewer splatUrl={`/api/jobs/${id}/splat`} />
          </div>

          <h2 style={{ marginTop: 28 }}>Embed it</h2>
          <p style={{ opacity: 0.8 }}>
            Drop this snippet into any website to show the splat:
          </p>
          <EmbedSnippet src={embedSrc} />
        </>
      )}
    </main>
  );
}
