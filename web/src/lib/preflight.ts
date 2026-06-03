/**
 * Client-side pre-flight checks for object-capture image sets.
 *
 * The thesis: for photos-in capture, the #1 driver of final quality is the
 * input set. Catching obviously-bad sets BEFORE we burn pipeline minutes saves
 * money and gives the user actionable feedback.
 */

export interface ImageStats {
  file: File;
  width: number;
  height: number;
  /** Variance of the Laplacian on a downsampled grayscale crop. Higher = sharper. */
  blurScore: number;
  thumbDataUrl: string;
}

export interface PreflightReport {
  count: number;
  stats: ImageStats[];
  warnings: string[];
  errors: string[];
}

const MIN_RECOMMENDED = 20;
const MIN_RESOLUTION = 720;       // shorter edge
const BLUR_WARN_THRESHOLD = 80;   // tuned empirically; lower = blurrier
const THUMB_MAX = 160;

export async function analyzeImage(file: File): Promise<ImageStats> {
  const bitmap = await createImageBitmap(file);
  const { width, height } = bitmap;

  // --- thumbnail ------------------------------------------------------------
  const scale = Math.min(1, THUMB_MAX / Math.max(width, height));
  const tw = Math.max(1, Math.round(width * scale));
  const th = Math.max(1, Math.round(height * scale));
  const canvas = document.createElement('canvas');
  canvas.width = tw;
  canvas.height = th;
  const ctx = canvas.getContext('2d')!;
  ctx.drawImage(bitmap, 0, 0, tw, th);
  const thumbDataUrl = canvas.toDataURL('image/jpeg', 0.7);

  // --- blur heuristic: variance of Laplacian on grayscale thumb -------------
  const img = ctx.getImageData(0, 0, tw, th);
  const gray = new Float32Array(tw * th);
  for (let i = 0, j = 0; i < img.data.length; i += 4, j += 1) {
    gray[j] = 0.299 * img.data[i] + 0.587 * img.data[i + 1] + 0.114 * img.data[i + 2];
  }
  let sum = 0;
  let sumSq = 0;
  let n = 0;
  for (let y = 1; y < th - 1; y += 1) {
    for (let x = 1; x < tw - 1; x += 1) {
      const idx = y * tw + x;
      // 4-neighbour Laplacian
      const lap =
        4 * gray[idx] -
        gray[idx - 1] -
        gray[idx + 1] -
        gray[idx - tw] -
        gray[idx + tw];
      sum += lap;
      sumSq += lap * lap;
      n += 1;
    }
  }
  const mean = sum / n;
  const blurScore = sumSq / n - mean * mean;

  bitmap.close?.();
  return { file, width, height, blurScore, thumbDataUrl };
}

export function reportFromStats(stats: ImageStats[]): PreflightReport {
  const warnings: string[] = [];
  const errors: string[] = [];

  if (stats.length === 0) {
    errors.push('No images selected.');
  } else if (stats.length < MIN_RECOMMENDED) {
    warnings.push(
      `Only ${stats.length} images — we recommend at least ${MIN_RECOMMENDED} from an orbit around the object for good reconstruction.`,
    );
  }

  const lowRes = stats.filter((s) => Math.min(s.width, s.height) < MIN_RESOLUTION);
  if (lowRes.length > 0) {
    warnings.push(
      `${lowRes.length} image(s) are below ${MIN_RESOLUTION}px on the short edge — quality will suffer.`,
    );
  }

  const blurry = stats.filter((s) => s.blurScore < BLUR_WARN_THRESHOLD);
  if (blurry.length > 0) {
    warnings.push(
      `${blurry.length} image(s) look blurry (low Laplacian variance). Re-shoot these for sharper splats.`,
    );
  }

  return { count: stats.length, stats, warnings, errors };
}
