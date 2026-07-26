import type {
  AccessConfig,
  AlbumEntry,
  FinalClaim,
  CacheStats,
  CreateSessionResponse,
  DeckFilters,
  DeckResponse,
  JoinResponse,
  LibraryFilters,
  LibraryStatus,
  MatchesResponse,
  PinPoll,
  PinStart,
  PlayerEntry,
  ProgressResponse,
  SessionStats,
  SessionSummary,
  SetupServerResponse,
  SetupStatus,
  SwipeResult,
} from "./types";

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : "Request failed");
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: init?.body ? { "Content-Type": "application/json" } : undefined,
    ...init,
  });
  if (!response.ok) {
    let detail: unknown = response.statusText;
    try {
      detail = (await response.json()).detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(response.status, detail);
  }
  return response.json() as Promise<T>;
}

export const api = {
  libraryStatus: () => request<LibraryStatus>("/api/library/status"),

  setupStatus: () => request<SetupStatus>("/api/setup/status"),

  startPin: () => request<PinStart>("/api/setup/pin", { method: "POST" }),

  pollPin: (pinId: string) => request<PinPoll>(`/api/setup/pin/${pinId}`),

  chooseServer: (body: {
    machine_id?: string;
    url?: string;
    token?: string;
    sections?: string[];
  }) =>
    request<SetupServerResponse>("/api/setup/server", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  triggerSync: (full = false) =>
    request<{ started: boolean }>("/api/library/sync", {
      method: "POST",
      body: JSON.stringify({ full }),
    }),

  cacheStats: () => request<CacheStats>("/api/settings/cache"),

  clearCache: () =>
    request<{ freed_bytes: number }>("/api/settings/cache/clear", {
      method: "POST",
    }),

  signOut: () => request<{ stage: string }>("/api/settings/signout", { method: "POST" }),

  accessConfig: () => request<AccessConfig>("/api/settings/access"),

  saveAccess: (localUrl: string, remoteUrl: string) =>
    request<AccessConfig>("/api/settings/access", {
      method: "PUT",
      body: JSON.stringify({ local_url: localUrl, remote_url: remoteUrl }),
    }),

  rejoin: (sessionId: string, participantId: string) =>
    request<JoinResponse>(`/api/sessions/${sessionId}/rejoin`, {
      method: "POST",
      body: JSON.stringify({ participant_id: participantId }),
    }),

  claimFinal: (sessionId: string) =>
    request<FinalClaim>(`/api/sessions/${sessionId}/final/claim`, { method: "POST" }),

  releaseFinal: (sessionId: string) =>
    request<FinalClaim>(`/api/sessions/${sessionId}/final/claim`, { method: "DELETE" }),

  vapidKey: () => request<{ public_key: string }>("/api/push/vapid"),

  subscribePush: (sessionId: string, subscription: PushSubscriptionJSON) =>
    request<{ subscribed: boolean }>(`/api/sessions/${sessionId}/push`, {
      method: "POST",
      body: JSON.stringify(subscription),
    }),

  lookupCode: (code: string) =>
    request<SessionSummary>(`/api/sessions/${encodeURIComponent(code)}`),

  sessionSummary: (sessionId: string) =>
    request<SessionSummary>(`/api/sessions/${sessionId}/summary`),

  join: (sessionId: string, displayName: string) =>
    request<JoinResponse>(`/api/sessions/${sessionId}/join`, {
      method: "POST",
      body: JSON.stringify({ display_name: displayName }),
    }),

  libraryFilters: () => request<LibraryFilters>("/api/library/filters"),

  previewCount: (filters: DeckFilters) => {
    const params = new URLSearchParams();
    params.set("unwatched_only", String(filters.unwatched_only));
    if (filters.genres.length) params.set("genres", filters.genres.join(","));
    if (filters.year_min != null) params.set("year_min", String(filters.year_min));
    if (filters.year_max != null) params.set("year_max", String(filters.year_max));
    if (filters.max_runtime != null) params.set("max_runtime", String(filters.max_runtime));
    if (filters.min_rating != null) params.set("min_rating", String(filters.min_rating));
    if (filters.certificate) params.set("certificate", filters.certificate);
    if (filters.collection) params.set("collection", filters.collection);
    params.set("media", filters.media);
    return request<{ count: number }>(`/api/filters/preview?${params}`);
  },

  createSession: (displayName: string, filters: DeckFilters, deckSize: number) =>
    request<CreateSessionResponse>("/api/sessions", {
      method: "POST",
      body: JSON.stringify({
        display_name: displayName,
        filters,
        deck_size: deckSize,
      }),
    }),

  deck: (sessionId: string) =>
    request<DeckResponse>(`/api/sessions/${sessionId}/deck`),

  postSwipes: (sessionId: string, swipes: { item_id: string; direction: 0 | 1 }[]) =>
    request<SwipeResult>(`/api/sessions/${sessionId}/swipes`, {
      method: "POST",
      body: JSON.stringify({ swipes }),
    }),

  undoSwipe: (sessionId: string, itemId: string) =>
    request<SwipeResult>(`/api/sessions/${sessionId}/swipes/${itemId}`, {
      method: "DELETE",
    }),

  matches: (sessionId: string) =>
    request<MatchesResponse>(`/api/sessions/${sessionId}/matches`),

  progress: (sessionId: string) =>
    request<ProgressResponse>(`/api/sessions/${sessionId}/progress`),

  stats: (sessionId: string) =>
    request<SessionStats>(`/api/sessions/${sessionId}/stats`),

  crown: (sessionId: string, itemId: string) =>
    request<{ crowned_item_id: string }>(`/api/sessions/${sessionId}/crown`, {
      method: "POST",
      body: JSON.stringify({ item_id: itemId }),
    }),

  saveToAlbum: (sessionId: string, itemId: string, crowned = false) =>
    request<AlbumEntry>(`/api/sessions/${sessionId}/album`, {
      method: "POST",
      body: JSON.stringify({ item_id: itemId, crowned }),
    }),

  album: () => request<{ entries: AlbumEntry[] }>("/api/album"),

  removeFromAlbum: (sessionId: string, itemId: string) =>
    request<{ entries: AlbumEntry[] }>(`/api/album/${sessionId}/${itemId}`, {
      method: "DELETE",
    }),

  players: () => request<{ players: PlayerEntry[] }>("/api/players"),

  playOn: (itemId: string, playerId: string) =>
    request<{ sent: boolean }>("/api/players/play", {
      method: "POST",
      body: JSON.stringify({ item_id: itemId, player_id: playerId }),
    }),
};

export function posterUrl(itemId: string, w = 600, h = 900): string {
  return `/api/art/${itemId}?kind=poster&w=${w}&h=${h}`;
}

export function backdropUrl(itemId: string, w = 1280, h = 720): string {
  return `/api/art/${itemId}?kind=backdrop&w=${w}&h=${h}`;
}
