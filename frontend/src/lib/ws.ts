/** Shared per-session WebSocket with exponential-backoff reconnect.
 * Notification-only: REST is the source of truth, so consumers refetch on
 * every (re)open rather than trusting the stream to be gapless. */

export interface LiveEvent {
  type: string;
  [key: string]: unknown;
}

type Listener = (event: LiveEvent) => void;
type OpenListener = () => void;

const MAX_BACKOFF_MS = 30_000;

export class SessionSocket {
  private listeners = new Set<Listener>();
  private openListeners = new Set<OpenListener>();
  private ws: WebSocket | null = null;
  private attempt = 0;
  private closed = false;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(private sessionId: string) {
    this.connect();
    document.addEventListener("visibilitychange", this.onVisible);
  }

  private onVisible = () => {
    // iOS kills sockets on backgrounding; reconnect the moment we're back.
    if (
      document.visibilityState === "visible" &&
      (!this.ws || this.ws.readyState === WebSocket.CLOSED)
    ) {
      this.attempt = 0;
      this.connect();
    }
  };

  private connect() {
    if (this.closed) return;
    const scheme = location.protocol === "https:" ? "wss" : "ws";
    this.ws = new WebSocket(
      `${scheme}://${location.host}/api/sessions/${this.sessionId}/live`,
    );
    this.ws.onopen = () => {
      this.attempt = 0;
      this.openListeners.forEach((listener) => listener());
    };
    this.ws.onmessage = (message) => {
      let event: LiveEvent;
      try {
        event = JSON.parse(message.data);
      } catch {
        return;
      }
      if (event.type === "ping") {
        this.ws?.send("pong");
        return;
      }
      this.listeners.forEach((listener) => listener(event));
    };
    this.ws.onclose = () => {
      if (!this.closed) this.scheduleReconnect();
    };
    this.ws.onerror = () => this.ws?.close();
  }

  private scheduleReconnect() {
    const delay = Math.min(MAX_BACKOFF_MS, 1000 * 2 ** this.attempt);
    this.attempt += 1;
    this.reconnectTimer = setTimeout(() => this.connect(), delay);
  }

  /** Fires on every event. Returns an unsubscribe function. */
  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  /** Fires on every (re)connect — the moment to refetch state. */
  onOpen(listener: OpenListener): () => void {
    this.openListeners.add(listener);
    if (this.ws?.readyState === WebSocket.OPEN) listener();
    return () => this.openListeners.delete(listener);
  }

  destroy() {
    this.closed = true;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    document.removeEventListener("visibilitychange", this.onVisible);
    this.ws?.close();
  }
}

const sockets = new Map<string, SessionSocket>();

/** One socket per session, shared across screens for the page's lifetime. */
export function sessionSocket(sessionId: string): SessionSocket {
  let socket = sockets.get(sessionId);
  if (!socket) {
    socket = new SessionSocket(sessionId);
    sockets.set(sessionId, socket);
  }
  return socket;
}
