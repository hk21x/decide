import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { TicketStub } from "../components/TicketStub";
import { api } from "../lib/api";
import type { AlbumEntry, MatchEntry } from "../lib/types";

/** The stub album: kept tickets from past movie nights. Sessions expire;
 * the stubs you chose to keep don't. */
export function AlbumScreen() {
  const [entries, setEntries] = useState<AlbumEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .album()
      .then((a) => setEntries(a.entries))
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Couldn't load the album."),
      );
  }, []);

  async function remove(entry: AlbumEntry) {
    if (!window.confirm(`Remove the ${entry.title} stub from the album?`)) return;
    const updated = await api.removeFromAlbum(entry.session_id, entry.item_id);
    setEntries(updated.entries);
  }

  function asMatchEntry(entry: AlbumEntry): MatchEntry {
    return {
      item: {
        id: entry.item_id,
        title: entry.title,
        year: entry.year,
        tagline: null,
        summary: null,
        runtime_min: entry.runtime_min,
        content_rating: entry.content_rating,
        audience_rating: null,
        genres: [],
        directors: [],
        cast: [],
        has_poster: false,
        has_backdrop: false,
      },
      matched_at: entry.matched_at,
      right_count: entry.names.length,
      participant_count: entry.names.length,
      right_names: entry.names,
    };
  }

  return (
    <div className="mx-auto min-h-dvh max-w-lg px-5 pb-16 pt-6">
      <header className="mb-6 flex items-baseline justify-between">
        <Link to="/" className="flex items-center gap-1 text-sm font-semibold text-spool">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
            <path
              d="M15 5l-7 7 7 7"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          Back
        </Link>
        <span className="text-xs uppercase tracking-[0.2em] text-fog">Stub album</span>
      </header>

      <h1 className="type-display text-xl text-stub">Movie nights, kept</h1>

      {error && <p className="mt-4 text-sm text-bulb">{error}</p>}

      {entries !== null && entries.length === 0 && (
        <div className="mt-10 text-center text-fog">
          <p>No stubs kept yet.</p>
          <p className="mt-1 text-sm">
            Match a film and tap Keep — your movie nights live here long after the
            sessions expire.
          </p>
        </div>
      )}

      {entries !== null && entries.length > 0 && (
        <ul className="mt-6 space-y-4">
          {entries.map((entry) => (
            <li key={`${entry.session_id}-${entry.item_id}`} className="list-none">
              <TicketStub entry={asMatchEntry(entry)} crowned={entry.crowned} />
              <button
                onClick={() => remove(entry)}
                className="mt-1 w-full text-center text-xs text-fog/50"
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
