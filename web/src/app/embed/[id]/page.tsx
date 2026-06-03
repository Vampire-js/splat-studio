'use client';

import dynamic from 'next/dynamic';

const SplatViewer = dynamic(() => import('@/components/SplatViewer'), { ssr: false });

export default function EmbedPage({ params }: { params: { id: string } }) {
  return (
    <div style={{ position: 'fixed', inset: 0, background: '#0b0d12' }}>
      <SplatViewer splatUrl={`/api/jobs/${params.id}/splat`} height="100%" />
    </div>
  );
}
