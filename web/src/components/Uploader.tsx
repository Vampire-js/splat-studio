'use client';

import { useCallback, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { analyzeImage, reportFromStats, type PreflightReport } from '@/lib/preflight';

export default function Uploader() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [report, setReport] = useState<PreflightReport | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onFiles = useCallback(async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    setError(null);
    setAnalyzing(true);
    setReport(null);
    try {
      const imageFiles = Array.from(files).filter((f) => f.type.startsWith('image/'));
      const stats = await Promise.all(imageFiles.map(analyzeImage));
      setReport(reportFromStats(stats));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setAnalyzing(false);
    }
  }, []);

  const onDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      onFiles(e.dataTransfer.files);
    },
    [onFiles],
  );

  const submit = useCallback(async () => {
    if (!report || report.stats.length === 0) return;
    setSubmitting(true);
    setError(null);
    try {
      const form = new FormData();
      for (const s of report.stats) form.append('images', s.file, s.file.name);
      const res = await fetch('/api/jobs', { method: 'POST', body: form });
      if (!res.ok) throw new Error(`Upload failed: ${res.status} ${await res.text()}`);
      const { id } = (await res.json()) as { id: string };
      router.push(`/jobs/${id}`);
    } catch (e) {
      setError((e as Error).message);
      setSubmitting(false);
    }
  }, [report, router]);

  return (
    <div>
      <div
        onDrop={onDrop}
        onDragOver={(e) => e.preventDefault()}
        onClick={() => inputRef.current?.click()}
        style={{
          border: '2px dashed #30363d',
          borderRadius: 12,
          padding: 40,
          textAlign: 'center',
          cursor: 'pointer',
          background: '#0d1117',
          color: '#c9d1d9',
        }}
      >
        <p style={{ margin: 0, fontSize: 16 }}>
          Drop a folder of photos here, or click to choose files.
        </p>
        <p style={{ margin: '8px 0 0', fontSize: 13, opacity: 0.7 }}>
          Tip: 30–150 photos in an orbit around the object works best.
        </p>
        <input
          ref={inputRef}
          type="file"
          accept="image/*"
          multiple
          // @ts-expect-error — non-standard but supported in Chromium/Edge for folder picking
          webkitdirectory=""
          directory=""
          hidden
          onChange={(e) => onFiles(e.target.files)}
        />
      </div>

      {analyzing && <p style={{ marginTop: 12 }}>Analyzing images…</p>}
      {error && (
        <p style={{ marginTop: 12, color: '#f85149' }}>
          {error}
        </p>
      )}

      {report && (
        <div style={{ marginTop: 20 }}>
          <p>
            <strong>{report.count}</strong> images selected
          </p>

          {report.errors.length > 0 && (
            <ul style={{ color: '#f85149' }}>
              {report.errors.map((e) => (
                <li key={e}>{e}</li>
              ))}
            </ul>
          )}
          {report.warnings.length > 0 && (
            <ul style={{ color: '#d29922' }}>
              {report.warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          )}

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(120px, 1fr))',
              gap: 8,
              marginTop: 12,
            }}
          >
            {report.stats.slice(0, 60).map((s, i) => (
              <div key={i} style={{ position: 'relative' }}>
                <img
                  src={s.thumbDataUrl}
                  alt={s.file.name}
                  style={{ width: '100%', borderRadius: 6, display: 'block' }}
                />
                <span
                  style={{
                    position: 'absolute',
                    bottom: 4,
                    left: 4,
                    background: 'rgba(0,0,0,0.6)',
                    color: 'white',
                    padding: '1px 5px',
                    borderRadius: 4,
                    fontSize: 10,
                  }}
                >
                  {s.width}×{s.height}
                </span>
              </div>
            ))}
            {report.stats.length > 60 && (
              <div style={{ alignSelf: 'center', opacity: 0.7 }}>
                +{report.stats.length - 60} more
              </div>
            )}
          </div>

          <button
            type="button"
            disabled={submitting || report.errors.length > 0}
            onClick={submit}
            style={{
              marginTop: 16,
              padding: '10px 18px',
              borderRadius: 8,
              border: 0,
              background: submitting ? '#30363d' : '#238636',
              color: 'white',
              fontWeight: 600,
              cursor: submitting ? 'not-allowed' : 'pointer',
            }}
          >
            {submitting ? 'Uploading…' : 'Create splat'}
          </button>
        </div>
      )}
    </div>
  );
}
