export type FaceBox = { x: number; y: number; width: number; height: number };
export const RECOVERABLE = ['NO_FACE', 'MULTIPLE_FACES', 'FACE_TOO_SMALL', 'LOW_LIGHT', 'OVEREXPOSED', 'BLURRY_FACE'];
export const STABLE_FRAMES = 3;
export const SAMPLE_COUNT = 5;
export function isStable(previous: FaceBox | null, current: FaceBox) {
  if (!previous) return false;
  return Math.abs(previous.x + previous.width / 2 - current.x - current.width / 2) < 0.04
    && Math.abs(previous.y + previous.height / 2 - current.y - current.height / 2) < 0.04
    && Math.abs(previous.width - current.width) / previous.width < 0.2
    && Math.abs(previous.height - current.height) / previous.height < 0.2;
}
export function median(values: number[]) {
  const ordered = [...values].sort((a, b) => a - b);
  return ordered[Math.floor(ordered.length / 2)];
}
