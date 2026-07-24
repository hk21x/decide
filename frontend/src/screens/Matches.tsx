import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { TicketStub } from "../components/TicketStub";
import { api } from "../lib/api";
import { openInPlex } from "../lib/plexLink";
import { getPid, savePid } from "../lib/session";
import type {
  MatchEntry,
  ProgressResponse,
  SessionSummary,
} from "../lib/types";
import { sessionSocket } from "../lib/ws";

export function MatchesScreen() {
  const { sessionId = "" } = useParams();
  const navigate = useNavigate();
  const [matches, setMatches] = useState<MatchEntry[] | null>(null);
  const [progress, setProgress] = useState<ProgressResponse | null>(null);
  const [session, setSession] = useState<SessionSummary | null>(null);
  const [machineId, setMachineId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const seen = useRef<Set<string> | null>(null); // null until first load
  const [newIds, setNewIds] = useState<Set<string>>(new Set());
  const socket = useMemo(() => sessionSocket(sessionId), [sessionId]);
  const myPid = getPid(sessionId);

  const refetch = useCallback(async () => {
    try {
      const [m, p] = await Promise.all([
        api.matches(sessionId),
        api.progress(sessionId),
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
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't load matches.");
    }
  }, [sessionId]);

  useEffect(() => {
    void refetch();
    api.sessionSummary(sessionId).then(setSession).catch(() => {});
    api.setupStatus().then((s) => setMachineId(s.machine_id)).catch(() => {});
    const offEvent = socket.subscribe((event) => {
      if (["match", "unmatch", "progress", "complete", "joined"].includes(event.type)) {
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
        <ul className="space-y-4">
          {matches.map((entry) => (
            <TicketStub
              key={entry.item.id}
              entry={entry}
              isNew={newIds.has(entry.item.id)}
              onOpen={
                machineId ? () => openInPlex(entry.item.id, machineId) : undefined
              }
            />
          ))}
        </ul>
      )}

      {matches !== null && matches.length > 0 && (
        <p className="mt-3 text-center text-xs text-fog/60">
          Tap a stub to open it in Plex.
        </p>
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
