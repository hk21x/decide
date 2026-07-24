import { api } from "./api";
import type { SwipeResult } from "./types";

type Swipe = { item_id: string; direction: 0 | 1 };

const BATCH_SIZE = 5;
const FLUSH_AFTER_MS = 2000;

/**
 * Batches swipes: sends at 5 pending or after 2 s, never one request per
 * swipe (brief §4.6). Pending swipes persist in localStorage, so a dead
 * spot or an app kill loses nothing — replay is safe because the server
 * upserts on a composite primary key (exactly-once by construction).
 */
export class SwipeQueue {
  private pending: Swipe[] = [];
  private timer: ReturnType<typeof setTimeout> | null = null;
  private inFlight = false;
  private storageKey: string;

  constructor(
    private sessionId: string,
    private onResult?: (result: SwipeResult) => void,
  ) {
    this.storageKey = `decide-queue-${sessionId}`;
    try {
      const stored = localStorage.getItem(this.storageKey);
      if (stored) this.pending = JSON.parse(stored) as Swipe[];
    } catch {
      /* corrupted storage — start clean */
    }
    window.addEventListener("online", this.onOnline);
    if (this.pending.length) void this.flush(); // survivors from last visit
  }

  private onOnline = () => void this.flush();

  private persist(): void {
    try {
      if (this.pending.length === 0) localStorage.removeItem(this.storageKey);
      else localStorage.setItem(this.storageKey, JSON.stringify(this.pending));
    } catch {
      /* storage full — the in-memory queue still works */
    }
  }

  add(itemId: string, direction: 0 | 1): void {
    this.pending.push({ item_id: itemId, direction });
    this.persist();
    if (this.pending.length >= BATCH_SIZE) {
      void this.flush();
    } else {
      this.timer ??= setTimeout(() => void this.flush(), FLUSH_AFTER_MS);
    }
  }

  /** Remove a not-yet-sent swipe (fast undo). True if it was still queued. */
  removePending(itemId: string): boolean {
    const before = this.pending.length;
    this.pending = this.pending.filter((swipe) => swipe.item_id !== itemId);
    if (this.pending.length < before) {
      this.persist();
      return true;
    }
    return false;
  }

  async flush(): Promise<void> {
    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }
    if (this.inFlight || this.pending.length === 0) return;
    const batch = this.pending;
    this.pending = [];
    this.inFlight = true;
    try {
      const result = await api.postSwipes(this.sessionId, batch);
      this.persist();
      this.onResult?.(result);
    } catch {
      this.pending = [...batch, ...this.pending]; // offline — keep for later
      this.persist();
      this.timer ??= setTimeout(() => void this.flush(), FLUSH_AFTER_MS);
    } finally {
      this.inFlight = false;
      if (this.pending.length >= BATCH_SIZE) void this.flush();
    }
  }

  destroy(): void {
    window.removeEventListener("online", this.onOnline);
    if (this.timer) clearTimeout(this.timer);
  }
}
