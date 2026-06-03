'use client';

import { useEffect, useRef } from 'react';

interface Props {
  /** Absolute or root-relative URL of a .ksplat/.ply/.splat file. */
  splatUrl: string;
  /** Optional fixed height; otherwise fills the parent. */
  height?: number | string;
}

/**
 * Thin React wrapper around @mkkellogg/gaussian-splats-3d's Viewer.
 *
 * The library is dynamically imported (and only on the client) because it
 * pulls in Three.js + WebGL state at module load.
 */
export default function SplatViewer({ splatUrl, height = '100%' }: Props) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const viewerRef = useRef<unknown>(null);

  useEffect(() => {
    let cancelled = false;
    let viewer: any = null;

    (async () => {
      const mod = await import('@mkkellogg/gaussian-splats-3d');
      if (cancelled || !hostRef.current) return;

      viewer = new mod.Viewer({
        rootElement: hostRef.current,
        cameraUp: [0, -1, 0],
        initialCameraPosition: [0, 1, -3],
        initialCameraLookAt: [0, 0, 0],
        sharedMemoryForWorkers: false, // safer for iframes / non-COOP+COEP hosts
      });
      viewerRef.current = viewer;

      try {
        // Our splat URL is API-route-style ("/api/jobs/.../splat") with no file
        // extension, so we tell the loader the format explicitly.
        // SceneFormat: { Splat: 0, KSplat: 1, Ply: 2, Spz: 3 } — see
        // node_modules/@mkkellogg/gaussian-splats-3d/src/loaders/SceneFormat.js
        await viewer.addSplatScene(splatUrl, {
          showLoadingUI: true,
          progressiveLoad: false,
          format: mod.SceneFormat?.Splat ?? 0,
        });
        if (cancelled) return;
        viewer.start();
      } catch (err) {
        // eslint-disable-next-line no-console
        console.error('Failed to load splat scene:', err);
      }
    })();

    return () => {
      cancelled = true;
      try {
        viewer?.dispose?.();
      } catch {
        /* ignore */
      }
      viewerRef.current = null;
    };
  }, [splatUrl]);

  return (
    <div
      ref={hostRef}
      style={{
        width: '100%',
        height,
        background: '#0b0d12',
        position: 'relative',
        overflow: 'hidden',
      }}
    />
  );
}
