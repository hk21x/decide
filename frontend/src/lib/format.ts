export function formatRuntime(minutes: number | null): string | null {
  if (minutes == null || minutes <= 0) return null;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (hours === 0) return `${rest}m`;
  if (rest === 0) return `${hours}h`;
  return `${hours}h ${rest}m`;
}

/** "gb/12A" -> "12A"; keeps bare certs as-is. */
export function formatCert(cert: string | null): string | null {
  if (!cert) return null;
  const bare = cert.includes("/") ? cert.split("/").pop()! : cert;
  return bare.toUpperCase() === "NOT RATED" ? null : bare;
}

export function formatRating(rating: number | null): string | null {
  if (rating == null) return null;
  return rating.toFixed(1);
}

import type { DeckFilters } from "./types";

/** Human-readable filter summary for the lobby. */
export function describeFilters(filters: DeckFilters): string {
  const parts: string[] = [];
  if (filters.unwatched_only) parts.push("unwatched only");
  if (filters.genres.length) parts.push(filters.genres.join(" / "));
  if (filters.year_min != null || filters.year_max != null) {
    parts.push(
      `${filters.year_min ?? "…"}–${filters.year_max ?? "…"}`.replace("–…", " on"),
    );
  }
  if (filters.max_runtime != null) parts.push(`under ${filters.max_runtime} min`);
  if (filters.min_rating != null) parts.push(`rated ${filters.min_rating}+`);
  if (filters.certificate) parts.push(`certificate ${filters.certificate} or below`);
  return parts.length ? parts.join(" · ") : "the whole library";
}
