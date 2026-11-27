/**
 * Камерын live preview-ийн хайрцгуудыг кадраас кадрт тогтвортой байлгана. Кадр бүрийн detection бага зэрэг
 * өөр байдаг (дараалал солигдох, хайрцаг нэг кадрт алга болох) тул шууд зурвал хүрээ анивчина. Тиймээс
 * хайрцгийг өмнөх кадрынхтай IoU-гоор тааруулж, тогтмол `id` өгнө (UI `id`-г key болгож, CSS transition-оор
 * зөөлөн хөдөлгөнө). Алга болсон хайрцгийг ч хэдэн кадрын турш хадгална.
 */

export type Box = { x: number; y: number; width: number; height: number };
export type Detection = { box: Box; score: number };
export type TrackedRegion = { id: number; box: Box; score: number };

type Track = TrackedRegion & { misses: number };

/** Хоёр хайрцгийн давхцлын харьцаа (intersection over union), 0..1. */
export function iou(a: Box, b: Box): number {
  const width = Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x);
  const height = Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y);
  if (width <= 0 || height <= 0) return 0;
  const overlap = width * height;
  return overlap / (a.width * a.height + b.width * b.height - overlap);
}

export class RegionTracker {
  private tracks: Track[] = [];
  private nextId = 1;

  /**
   * @param minIou  хоёр кадрын хайрцгийг нэг зүйл гэж үзэх хамгийн бага давхцал
   * @param maxMisses  хайрцаг хэдэн дараалсан кадрт алга болтол хадгалагдах вэ
   */
  constructor(
    private readonly minIou = 0.3,
    private readonly maxMisses = 2,
  ) {}

  /** Шинэ кадрын detection-ийг оруулж, одоо харуулах хайрцгуудыг буцаана. */
  update(detections: Detection[]): TrackedRegion[] {
    const pairs: { track: number; detection: number; overlap: number }[] = [];
    this.tracks.forEach((track, t) =>
      detections.forEach((detection, d) => {
        const overlap = iou(track.box, detection.box);
        if (overlap >= this.minIou) pairs.push({ track: t, detection: d, overlap });
      }),
    );
    pairs.sort((a, b) => b.overlap - a.overlap);

    const usedTracks = new Set<number>();
    const usedDetections = new Set<number>();
    for (const { track, detection } of pairs) {
      if (usedTracks.has(track) || usedDetections.has(detection)) continue;
      usedTracks.add(track);
      usedDetections.add(detection);
      const found = detections[detection]!;
      this.tracks[track] = { ...this.tracks[track]!, box: found.box, score: found.score, misses: 0 };
    }

    const kept = this.tracks
      .map((track, t) => (usedTracks.has(t) ? track : { ...track, misses: track.misses + 1 }))
      .filter((track) => track.misses <= this.maxMisses);
    detections.forEach((detection, d) => {
      if (!usedDetections.has(d)) kept.push({ id: this.nextId++, misses: 0, ...detection });
    });
    this.tracks = kept;
    return kept.map(({ id, box, score }) => ({ id, box, score }));
  }

  reset(): void {
    this.tracks = [];
  }
}
