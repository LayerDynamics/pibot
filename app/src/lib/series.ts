/**
 * Bounded time-series for policy-link latency samples.
 * Keeps a rolling window of at most MAX_SAMPLES entries; older entries
 * are dropped when the window is full (drop-oldest).
 */

export const MAX_SAMPLES = 200;
export const STALE_THRESHOLD_MS = 1000;

export interface LatencySample {
  ts: number;       // monotonic timestamp (Date.now() / 1000 or snapshot.ts)
  inferMs: number;  // last_inference_ms
  stale: boolean;   // true when chunk_age_ms > STALE_THRESHOLD_MS at this sample
}

export class LatencySeries {
  private _samples: LatencySample[] = [];

  push(sample: LatencySample): void {
    if (this._samples.length >= MAX_SAMPLES) {
      this._samples.shift();
    }
    this._samples.push(sample);
  }

  get samples(): readonly LatencySample[] {
    return this._samples;
  }

  get length(): number {
    return this._samples.length;
  }

  isCurrentlyStale(): boolean {
    if (this._samples.length === 0) return false;
    return this._samples[this._samples.length - 1].stale;
  }

  clear(): void {
    this._samples = [];
  }
}
