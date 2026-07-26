// Mirrors backend/src/matinee/models.py

export interface DeckFilters {
  unwatched_only: boolean;
  genres: string[];
  year_min: number | null;
  year_max: number | null;
  max_runtime: number | null;
  min_rating: number | null;
  certificate: "U" | "PG" | "12A" | "15" | "18" | null;
  collection: string | null;
  media: "films" | "series";
}

export const defaultFilters: DeckFilters = {
  unwatched_only: true,
  genres: [],
  year_min: null,
  year_max: null,
  max_runtime: null,
  min_rating: null,
  certificate: null,
  collection: null,
  media: "films",
};

export interface LibraryFilters {
  genres: string[];
  decades: number[];
  certificates: string[];
  collections: string[];
}

export interface LibraryStatus {
  stage: string;
  state: string;
  kind: string | null;
  processed: number;
  total: number | null;
  error: string | null;
  item_count: number;
  unusable_count: number;
  last_synced_at: number | null;
  sections: string[] | null;
}

export interface CreateSessionResponse {
  id: string;
  join_code: string;
  deck_size: number;
  participant_id: string;
  expires_at: number;
}

export interface DeckItem {
  id: string;
  title: string;
  year: number | null;
  tagline: string | null;
  summary: string | null;
  runtime_min: number | null;
  content_rating: string | null;
  audience_rating: number | null;
  genres: string[];
  directors: string[];
  cast: { name: string; role: string | null }[];
  has_poster: boolean;
  has_backdrop: boolean;
  media_type: "movie" | "show";
  seasons: number | null;
}

export interface DeckResponse {
  session_id: string;
  deck_size: number;
  items: DeckItem[];
}

export interface SwipeResult {
  accepted: number;
  new_matches: string[];
  removed_matches: string[];
}

export interface MatchEntry {
  item: DeckItem;
  matched_at: number;
  right_count: number;
  participant_count: number;
  right_names: string[];
}

export interface SetupStatus {
  stage: string;
  server_name: string | null;
  machine_id: string | null;
  sections: string[] | null;
}

export interface PinStart {
  id: string;
  code: string;
  link_url: string;
}

export interface ServerEntry {
  name: string;
  machine_id: string;
  owned: boolean;
}

export interface PinPoll {
  authenticated: boolean;
  expired: boolean;
  servers: ServerEntry[] | null;
}

export interface SectionEntry {
  key: string;
  title: string;
  movie_count: number;
  type: "movie" | "show";
}

export interface SetupServerResponse {
  stage: string;
  server_name: string | null;
  machine_id: string | null;
  available_sections: SectionEntry[] | null;
}

export interface CacheStats {
  entries: number;
  bytes: number;
  cap_bytes: number;
}

export interface ParticipantEntry {
  id: string;
  display_name: string;
  joined_at: number;
}

export interface SessionSummary {
  id: string;
  join_code: string;
  state: string;
  deck_size: number;
  created_at: number;
  expires_at: number;
  participants: ParticipantEntry[];
  filters: DeckFilters;
  crowned_item_id: string | null;
}

export interface JoinResponse {
  participant_id: string;
  session: SessionSummary;
}

export interface MatchesResponse {
  session_id: string;
  matches: MatchEntry[];
}

export interface ProgressEntry {
  participant_id: string;
  display_name: string;
  swiped: number;
  total: number;
}

export interface ProgressResponse {
  session_id: string;
  state: string;
  deck_size: number;
  participants: ProgressEntry[];
  match_count: number;
  all_complete: boolean;
}

export interface TooFewFilms {
  error: "too_few_films";
  count: number;
  culprit: string | null;
  would_yield: number | null;
  message: string;
}

export interface PairStat {
  a_id: string;
  a_name: string;
  b_id: string;
  b_name: string;
  both_swiped: number;
  agreed: number;
  both_right: number;
  pct: number;
}

export interface SessionStats {
  session_id: string;
  deck_size: number;
  pairs: PairStat[];
}

export interface AlbumEntry {
  session_id: string;
  item_id: string;
  title: string;
  year: number | null;
  runtime_min: number | null;
  content_rating: string | null;
  names: string[];
  matched_at: number;
  saved_at: number;
  crowned: boolean;
}

export interface PlayerEntry {
  id: string;
  name: string;
  product: string | null;
}

export interface AccessConfig {
  local_url: string | null;
  remote_url: string | null;
  detected_local: string | null;
  detected_remote: string | null;
}

export interface FinalClaim {
  mine: boolean;
  holder_name: string | null;
}
