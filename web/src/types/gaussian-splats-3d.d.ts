// The @mkkellogg/gaussian-splats-3d package ships no TypeScript types.
// We declare just the surface we use to keep TS happy.
declare module '@mkkellogg/gaussian-splats-3d' {
  export const SceneFormat: {
    Splat: 0;
    KSplat: 1;
    Ply: 2;
    Spz: 3;
  };

  export class Viewer {
    constructor(opts: Record<string, unknown>);
    addSplatScene(path: string, opts?: Record<string, unknown>): Promise<void>;
    addSplatScenes(scenes: unknown[], showLoadingUI?: boolean): Promise<void>;
    start(): void;
    dispose?(): void;
  }

  export class DropInViewer {
    constructor(opts?: Record<string, unknown>);
    addSplatScenes(scenes: unknown[], showLoadingUI?: boolean): Promise<void>;
  }
}
