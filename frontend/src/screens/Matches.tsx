import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { PosterImg } from "../components/PosterImg";
import { TicketStub } from "../components/TicketStub";
import { api } from "../lib/api";
import { openInPlex } from "../lib/plexLink";
import { getPid, savePid } from "../lib/session";
import type {
  MatchEntry,
  ProgressResponse,
  SessionStats,
  SessionSummary,
} from "../lib/types";
import { sessionSocket } from "../lib/ws";

export function MatchesScreen() {
  const { sessionId = "" } = useParams();
  const navigate = useNavigate();
  const [matches, setMatches] = useState<MatchEntry[] | null>(null);
  const [progress, setProgress] = useState<ProgressResponse | null>(null);
  const [session, setSession] = useState<SessionSummary | null>(null);
  const [stats, setStats] = useState<SessionStats | null>(null);
  const [kept, setKept] = useState<Set<string>>(new Set());
  const [machineId, setMachineId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const seen = useRef<Set<string> | null>(null); // null until first load
  const [newIds, setNewIds] = useState<Set<string>>(new Set());
  const socket = useMemo(() => sessionSocket(sessionId), [sessionId]);
  const myPid = getPid(sessionId);

  const refetch = useCallback(async () => {
    try {
      const [m, p, s, st] = await Promise.all([
        api.matches(sessionId),
        api.progress(sessionId),
        api.sessionSummary(sessionId),
        api.stats(sessionId),
      ]);
      // First load prints nothing; later arrivals get the printer feed.
      if (seen.current === null) {
        seen.current = new Set(m.matches.map((entry) => entry.item.id));
      } else {
        const fresh = new Set<string>();
        for (const entry of m.matches) {
          if (!seen.current.has(entry.item.id)) {
            fresh.add(entry.item.id);
            seen.current.add(entry.item.id);
          }
        }
        if (fresh.size) setNewIds(fresh);
      }
      setMatches(m.matches);
      setProgress(p);
      setSession(s);
      setStats(st);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't load matches.");
    }
  }, [sessionId]);

  useEffect(() => {
    void refetch();
    api.setupStatus().then((s) => setMachineId(s.machine_id)).catch(() => {});
    api
      .album()
      .then((a) =>
        setKept(
          new Set(
            a.entries
              .filter((entry) => entry.session_id === sessionId)
              .map((entry) => entry.item_id),
          ),
        ),
      )
      .catch(() => {});
    const offEvent = socket.subscribe((event) => {
      if (
        ["match", "unmatch", "progress", "complete", "joined", "crowned"].includes(
          event.type,
        )
      ) {
        void refetch();
      }
    });
    const offOpen = socket.onOpen(() => void refetch());
    return () => {
      offEvent();
      offOpen();
    };
  }, [sessionId, socket, refetch]);

  const me = progress?.participants.find((p) => p.participant_id === myPid);
  const others = progress?.participants.filter((p) => p.participant_id !== myPid) ?? [];
  const iAmDone = me != null && me.swiped >= me.total;
  const crownedEntry =
    session?.crowned_item_id != null
      ? matches?.find((entry) => entry.item.id === session.crowned_item_id) ?? null
      : null;

  async function keepStub(entry: MatchEntry, crowned = false) {
    try {
      await api.saveToAlbum(sessionId, entry.item.id, crowned);
      setKept((prev) => new Set(prev).add(entry.item.id));
    } catch {
      /* non-fatal */
    }
  }

  async function crownOnly(entry: MatchEntry) {
    try {
      await api.crown(sessionId, entry.item.id);
      void refetch();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't crown that film.");
    }
  }

  async function runAgain() {
    if (!session) return;
    setBusy(true);
    try {
      const fresh = await api.createSession(
        me?.display_name ?? "Host",
        session.filters,
        session.deck_size as 20 | 30 | 50,
      );
      savePid(fresh.id, fresh.participant_id);
      navigate(`/session/${fresh.id}/lobby`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't start a new session.");
    } finally {
      setBusy(false);
    }
  }

  const tasteLines = (stats?.pairs ?? [])
    .filter((pair) => pair.both_swiped >= 5)
    .map((pair) => {
      const a = pair.a_id === myPid ? "You" : pair.a_name;
      const b = pair.b_id === myPid ? "you" : pair.b_name;
      return `${a} and ${b} agreed on ${pair.agreed} of ${pair.both_swiped} — ${pair.pct}% compatible tonight.`;
    });

  return (
    <div className="mx-auto min-h-dvh max-w-lg px-5 pb-16 pt-6">
      <header className="mb-6 flex items-baseline justify-between">
        <Link to="/" className="text-lg font-bold tracking-tight text-spool">
          decide
        </Link>
        {session && (
          <span className="type-mono text-xs tracking-[0.2em] text-fog">
            {session.join_code}
          </span>
        )}
      </header>

      {crownedEntry && (
        <section className="mb-6 overflow-hidden rounded-2xl bg-riser">
          <div className="flex gap-4 p-4">
            <PosterImg
              itemId={crownedEntry.item.id}
              title={crownedEntry.item.title}
              className="w-24 shrink-0 rounded-lg"
              eager
            />
            <div className="min-w-0 py-1">
              <p className="type-mono text-[10px] uppercase tracking-[0.25em] text-bulb">
                👑 Tonight's film
              </p>
              <h2 className="type-display mt-1 text-xl text-stub">
                {crownedEntry.item.title}
              </h2>
              <div className="mt-3 flex flex-wrap gap-2">
                {machineId && (
                  <button
                    onClick={() => openInPlex(crownedEntry.item.id, machineId)}
                    className="rounded-xl bg-bulb px-4 py-2 text-sm font-semibold text-press"
                  >
                    Open in Plex
                  </button>
                )}
                {!kept.has(crownedEntry.item.id) && (
                  <button
                    onClick={() => keepStub(crownedEntry, true)}
                    className="rounded-xl border border-hairline px-4 py-2 text-sm font-semibold text-fog"
                  >
                    Keep the stub
                  </button>
                )}
              </div>
            </div>
          </div>
        </section>
      )}

      {progress && (
        <section className="mb-6 rounded-2xl bg-riser px-5 py-4">
          <h1 className="type-display text-xl text-stub">
            {iAmDone ? "That's your deck done" : "Matches so far"}
          </h1>
          <ul className="type-mono mt-3 space-y-1 text-sm text-fog">
            {progress.participants.map((participant) => {
              const done = participant.swiped >= participant.total;
              const left = participant.total - participant.swiped;
              return (
                <li key={participant.participant_id} className="flex justify-between">
                  <span>
                    {participant.display_name}
                    {participant.participant_id === myPid ? " (you)" : ""}
                  </span>
                  <span className={done ? "text-stub/80" : ""}>
                    {participant.swiped} / {participant.total}
                    {!done && participant.participant_id !== myPid
                      ? ` · ${left} left`
                      : ""}
                  </span>
                </li>
              );
            })}
          </ul>
          {tasteLines.length > 0 && (
            <div className="mt-3 border-t border-hairline pt-3 text-sm text-fog">
              {tasteLines.map((line) => (
                <p key={line}>{line}</p>
              ))}
            </div>
          )}
        </section>
      )}

      {error && <p className="mb-4 text-sm text-bulb">{error}</p>}

      {matches !== null && matches.length === 0 && (
        <div className="mt-10 text-center text-fog">
          <p>Nothing you've all said yes to — yet.</p>
          <p className="mt-1 text-sm">
            {others.some((p) => p.swiped < p.total)
              ? "The others are still swiping; matches land here the moment you agree."
              : "Try another deck with looser filters — drop the minimum rating, or let watched films back in."}
          </p>
        </div>
      )}

      {matches !== null && matches.length > 0 && (
        <>
          {!crownedEntry && (
            <div className="mb-4">
              {matches.length >= 2 ? (
                <Link
                  to={`/session/${sessionId}/final`}
                  className="type-display block rounded-2xl border-2 border-bulb py-3.5 text-center text-lg uppercase tracking-wide text-bulb"
                >
                  Final round — crown one
                </Link>
              ) : (
                <button
                  onClick={() => crownOnly(matches[0])}
                  className="type-display block w-full rounded-2xl border-2 border-bulb py-3.5 text-center text-lg uppercase tracking-wide text-bulb"
                >
                  Crown tonight's film
                </button>
              )}
            </div>
          )}

          <ul className="space-y-4">
            {matches.map((entry) => (
              <TicketStub
                key={entry.item.id}
                entry={entry}
                isNew={newIds.has(entry.item.id)}
                crowned={entry.item.id === session?.crowned_item_id}
                kept={kept.has(entry.item.id)}
                onKeep={() => keepStub(entry)}
                onOpen={
                  machineId ? () => openInPlex(entry.item.id, machineId) : undefined
                }
              />
            ))}
          </ul>
          <p className="mt-3 text-center text-xs text-fog/60">
            Tap a stub to open it in Plex · Keep saves it to your album.
          </p>
        </>
      )}

      <div className="mt-10 flex flex-col gap-3">
        {!iAmDone && (
          <Link
            to={`/session/${sessionId}/swipe`}
            className="rounded-2xl bg-bulb px-5 py-3.5 text-center font-semibold text-press"
          >
            Keep swiping
          </Link>
        )}
        <button
          onClick={runAgain}
          disabled={busy || !session}
          className="rounded-2xl bg-riser px-5 py-3.5 font-semibold text-stub disabled:opacity-40"
        >
          {busy ? "Building a new deck…" : "Run it again with the same filters"}
        </button>
        <Link to="/" className="text-center text-sm text-fog">
          Back to the start
        </Link>
      </div>
    </div>
  );
}
