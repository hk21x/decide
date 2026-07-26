import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { api, ApiError } from "../lib/api";
import { MOODS, type Mood } from "../lib/moods";
import { getName, recordSession, saveName, savePid } from "../lib/session";
import {
  defaultFilters,
  type DeckFilters,
  type LibraryFilters,
  type TooFewFilms,
} from "../lib/types";

const RUNTIME_OPTIONS = [null, 90, 120, 150] as const;
const RATING_OPTIONS = [null, 6, 7, 8] as const;
const SIZE_OPTIONS = [20, 30, 50] as const;
const CULPRIT_CLEAR: Record<string, Partial<DeckFilters>> = {
  unwatched_only: { unwatched_only: false },
  genres: { genres: [] },
  year_range: { year_min: null, year_max: null },
  max_runtime: { max_runtime: null },
  min_rating: { min_rating: null },
  certificate: { certificate: null },
  collection: { collection: null },
};

export function SetupScreen() {
  const navigate = useNavigate();
  const solo = useLocation().pathname === "/solo";
  const [available, setAvailable] = useState<LibraryFilters | null>(null);
  const [filters, setFilters] = useState<DeckFilters>(defaultFilters);
  const [deckSize, setDeckSize] = useState<20 | 30 | 50>(30);
  const [displayName, setDisplayName] = useState<string>(getName());
  const [count, setCount] = useState<number | null>(null);
  const [shortfall, setShortfall] = useState<TooFewFilms | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.libraryFilters().then(setAvailable).catch(() => setAvailable(null));
  }, []);

  // Live "N films match" counter, debounced (brief §7).
  useEffect(() => {
    setCount(null);
    const timer = setTimeout(() => {
      api
        .previewCount(filters)
        .then((r) => setCount(r.count))
        .catch(() => setCount(null));
    }, 250);
    return () => clearTimeout(timer);
  }, [filters]);

  const patch = (update: Partial<DeckFilters>) => {
    setShortfall(null);
    setError(null);
    setFilters((f) => ({ ...f, ...update }));
  };

  const toggleGenre = (genre: string) =>
    patch({
      genres: filters.genres.includes(genre)
        ? filters.genres.filter((g) => g !== genre)
        : [...filters.genres, genre],
    });

  // Moods, narrowed to genres this library actually has. A mood reads as
  // active when every one of its genres is ticked — so manual fine-tuning
  // and mood presets compose without separate bookkeeping.
  const moods = useMemo(() => {
    const inLibrary = new Set(available?.genres ?? []);
    return MOODS.map((mood) => ({
      ...mood,
      genres: mood.genres.filter((genre) => inLibrary.has(genre)),
    })).filter((mood) => mood.genres.length > 0);
  }, [available]);

  const isMoodActive = (mood: Mood) =>
    mood.genres.every((genre) => filters.genres.includes(genre));

  const toggleMood = (mood: Mood) => {
    if (isMoodActive(mood)) {
      // Untick this mood's genres, except any a still-active mood needs.
      const stillNeeded = new Set(
        moods
          .filter((other) => other.id !== mood.id && isMoodActive(other))
          .flatMap((other) => other.genres),
      );
      patch({
        genres: filters.genres.filter(
          (genre) => !mood.genres.includes(genre) || stillNeeded.has(genre),
        ),
      });
    } else {
      patch({ genres: [...new Set([...filters.genres, ...mood.genres])] });
    }
  };

  async function start() {
    const name = solo ? "Solo" : displayName.trim();
    if (!solo && !name) {
      setError("Add your name so the others know who's swiping.");
      return;
    }
    setBusy(true);
    setError(null);
    setShortfall(null);
    try {
      const session = await api.createSession(name, filters, deckSize);
      savePid(session.id, session.participant_id);
      recordSession({ id: session.id, code: session.join_code, deck_size: session.deck_size });
      if (!solo) saveName(name);
      navigate(
        solo ? `/session/${session.id}/swipe` : `/session/${session.id}/lobby`,
      );
    } catch (err) {
      if (err instanceof ApiError && typeof err.detail === "object" && err.detail) {
        setShortfall(err.detail as TooFewFilms);
      } else {
        setError(err instanceof Error ? err.message : "Couldn't start the session.");
      }
    } finally {
      setBusy(false);
    }
  }

  const countLine = useMemo(() => {
    if (count === null) return "…";
    return `${count.toLocaleString("en-GB")} film${count === 1 ? "" : "s"} match`;
  }, [count]);

  return (
    <div className="mx-auto min-h-dvh max-w-lg px-5 pb-28 pt-6">
      <header className="mb-6 flex items-center justify-between">
        <Link to="/" className="text-lg font-bold tracking-tight text-spool">
          decide
        </Link>
        <span
          className={`type-mono text-sm ${count !== null && count < 10 ? "text-bulb" : "text-fog"}`}
        >
          {countLine}
        </span>
      </header>

      <h1 className="type-display text-xl text-stub">
        {solo ? "Tonight's deck" : "Start a session"}
      </h1>
      <p className="mt-1 text-sm text-fog">
        Narrow the library down before you swipe — a deck is {deckSize} cards, not
        the whole shelf.
      </p>

      <section className="mt-6 space-y-6">
        {!solo && (
          <div>
            <h2 className="mb-2 text-sm font-semibold text-stub/80">Your name</h2>
            <input
              type="text"
              value={displayName}
              maxLength={40}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="Who's hosting tonight?"
              className="w-full rounded-xl border border-hairline bg-riser px-4 py-3 text-stub placeholder:text-fog/50"
            />
          </div>
        )}
        <div>
          <h2 className="mb-2 text-sm font-semibold text-stub/80">Tonight we're picking</h2>
          <div className="flex gap-2">
            {(
              [
                ["films", "🎬 A film"],
                ["series", "📺 A series"],
              ] as const
            ).map(([value, label]) => (
              <button
                key={value}
                onClick={() => patch({ media: value })}
                aria-pressed={filters.media === value}
                className={`flex-1 rounded-xl border py-2.5 text-sm ${
                  filters.media === value
                    ? "border-bulb bg-bulb/10 text-bulb"
                    : "border-hairline text-fog"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        <div>
          <h2 className="mb-2 text-sm font-semibold text-stub/80">Deck size</h2>
          <div className="flex gap-2">
            {SIZE_OPTIONS.map((size) => (
              <button
                key={size}
                onClick={() => setDeckSize(size)}
                className={`type-mono flex-1 rounded-xl border py-2.5 text-sm ${
                  deckSize === size
                    ? "border-bulb bg-bulb/10 text-bulb"
                    : "border-hairline text-fog"
                }`}
              >
                {size}
              </button>
            ))}
          </div>
        </div>

        <label className="flex items-center justify-between rounded-xl bg-riser px-4 py-3">
          <span className="text-sm text-stub/90">Unwatched only</span>
          <input
            type="checkbox"
            checked={filters.unwatched_only}
            onChange={(e) => patch({ unwatched_only: e.target.checked })}
            className="h-5 w-5 accent-[#F2637A]"
          />
        </label>

        {filters.media === "films" && (
        <div>
          <h2 className="mb-2 text-sm font-semibold text-stub/80">Max runtime</h2>
          <div className="flex gap-2">
            {RUNTIME_OPTIONS.map((option) => (
              <button
                key={String(option)}
                onClick={() => patch({ max_runtime: option })}
                className={`flex-1 rounded-xl border py-2.5 text-sm ${
                  filters.max_runtime === option
                    ? "border-bulb bg-bulb/10 text-bulb"
                    : "border-hairline text-fog"
                }`}
              >
                {option === null ? "Any" : <span className="type-mono">{option}m</span>}
              </button>
            ))}
          </div>
        </div>
        )}

        <div>
          <h2 className="mb-2 text-sm font-semibold text-stub/80">Minimum rating</h2>
          <div className="flex gap-2">
            {RATING_OPTIONS.map((option) => (
              <button
                key={String(option)}
                onClick={() => patch({ min_rating: option })}
                className={`flex-1 rounded-xl border py-2.5 text-sm ${
                  filters.min_rating === option
                    ? "border-bulb bg-bulb/10 text-bulb"
                    : "border-hairline text-fog"
                }`}
              >
                {option === null ? "Any" : <span className="type-mono">{option}+</span>}
              </button>
            ))}
          </div>
        </div>

        <div>
          <h2 className="mb-2 text-sm font-semibold text-stub/80">Certificate ceiling</h2>
          <div className="flex gap-2">
            {[null, ...(available?.certificates ?? ["U", "PG", "12A", "15", "18"])].map(
              (option) => (
                <button
                  key={String(option)}
                  onClick={() =>
                    patch({ certificate: option as DeckFilters["certificate"] })
                  }
                  className={`flex-1 rounded-xl border py-2.5 text-sm ${
                    filters.certificate === option
                      ? "border-bulb bg-bulb/10 text-bulb"
                      : "border-hairline text-fog"
                  }`}
                >
                  {option ?? "Any"}
                </button>
              ),
            )}
          </div>
        </div>

        {available && available.collections.length > 0 && (
          <div>
            <h2 className="mb-2 text-sm font-semibold text-stub/80">
              From a collection
            </h2>
            <select
              value={filters.collection ?? ""}
              onChange={(e) => patch({ collection: e.target.value || null })}
              className="w-full rounded-xl border border-hairline bg-riser px-4 py-3 text-stub"
            >
              <option value="">Any — the whole library</option>
              {available.collections.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </div>
        )}

        {available && available.genres.length > 0 && (
          <div>
            <h2 className="mb-2 text-sm font-semibold text-stub/80">In the mood for…</h2>
            <div className="flex flex-wrap gap-2">
              {moods.map((mood) => {
                const active = isMoodActive(mood);
                return (
                  <button
                    key={mood.id}
                    onClick={() => toggleMood(mood)}
                    aria-pressed={active}
                    className={`flex items-center gap-1.5 rounded-xl border px-3 py-2 text-sm ${
                      active
                        ? "border-bulb bg-bulb/10 text-bulb"
                        : "border-hairline text-fog"
                    }`}
                  >
                    <span aria-hidden>{mood.emoji}</span>
                    {mood.label}
                  </button>
                );
              })}
            </div>

            {filters.genres.length > 0 && (
              <p className="mt-3 text-xs text-fog">
                Ticked for you: {filters.genres.join(" · ")}{" "}
                <button
                  onClick={() => patch({ genres: [] })}
                  className="ml-1 font-semibold text-bulb"
                >
                  Clear
                </button>
              </p>
            )}

            <details className="mt-3">
              <summary className="cursor-pointer text-xs text-fog/70">
                Fine-tune genres
              </summary>
              <div className="mt-2 flex flex-wrap gap-2">
                {available.genres.map((genre) => (
                  <button
                    key={genre}
                    onClick={() => toggleGenre(genre)}
                    className={`rounded-full border px-3 py-1.5 text-xs ${
                      filters.genres.includes(genre)
                        ? "border-bulb bg-bulb/10 text-bulb"
                        : "border-hairline text-fog"
                    }`}
                  >
                    {genre}
                  </button>
                ))}
              </div>
            </details>
          </div>
        )}
      </section>

      {shortfall && (
        <div className="mt-6 rounded-xl border border-bulb/40 bg-bulb/10 p-4 text-sm text-stub">
          <p>{shortfall.message}</p>
          {shortfall.culprit && CULPRIT_CLEAR[shortfall.culprit] && (
            <button
              onClick={() => patch(CULPRIT_CLEAR[shortfall.culprit!])}
              className="mt-2 font-semibold text-bulb"
            >
              Remove that filter
            </button>
          )}
        </div>
      )}
      {error && <p className="mt-6 text-sm text-bulb">{error}</p>}

      <div className="fixed inset-x-0 bottom-0 bg-gradient-to-t from-house via-house/95 to-transparent px-5 pb-6 pt-8">
        <button
          onClick={start}
          disabled={busy || count === 0}
          className="mx-auto block w-full max-w-lg rounded-2xl bg-bulb py-4 font-semibold text-press transition-transform active:scale-[0.98] disabled:opacity-40"
        >
          {busy ? "Building the deck…" : solo ? "Start swiping" : "Create the session"}
        </button>
      </div>
    </div>
  );
}
