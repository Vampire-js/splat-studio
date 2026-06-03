'use client';

import { useCallback, useState } from 'react';

interface Props {
  src: string;
  width?: number;
  height?: number;
}

export default function EmbedSnippet({ src, width = 800, height = 600 }: Props) {
  const snippet = `<iframe src="${src}" width="${width}" height="${height}" frameborder="0" allow="fullscreen; xr-spatial-tracking" style="border:0;border-radius:12px;"></iframe>`;
  const [copied, setCopied] = useState(false);

  const copy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(snippet);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard blocked — user can copy manually */
    }
  }, [snippet]);

  return (
    <div>
      <pre
        style={{
          background: '#0e1117',
          color: '#e6edf3',
          padding: 12,
          borderRadius: 8,
          overflowX: 'auto',
          fontSize: 13,
          margin: 0,
        }}
      >
        {snippet}
      </pre>
      <button
        type="button"
        onClick={copy}
        style={{
          marginTop: 8,
          padding: '6px 12px',
          borderRadius: 6,
          border: '1px solid #30363d',
          background: copied ? '#238636' : '#21262d',
          color: '#e6edf3',
          cursor: 'pointer',
        }}
      >
        {copied ? 'Copied!' : 'Copy embed code'}
      </button>
    </div>
  );
}
