import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { JoinCodeBadge } from "../components/JoinCodeBadge";
import { api } from "../lib/api";
import { describeFilters } from "../lib/format";
import { getPid } from "../lib/session";
import type { SessionSummary } from "../lib/types";
import { sessionSocket } from "../lib/ws";

export function LobbyScreen() {
  const { sessionId = "" } = useParams();
  const navigate = useNavigate();
  const [session, setSession] = useState<SessionSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const myPid = getPid(sessionId);
  const socket = useMemo(() => sessionSocket(sessionId), [sessionId]);

  useEffect(() => {
    const refetch = () =>
      api
        .sessionSummary(sessionId)
        .then(setSession)
        .catch((err) =>
          setError(err instanceof Error ? err.message : "Couldn't load the session."),
        );
    refetch();
    const offEvent = socket.subscribe((event) => {
      if (event.type === "joined") refetch();
    });
    const offOpen = socket.onOpen(refetch);
    return () => {
      offEvent();
      offOpen();
    };
  }, [sessionId, socket]);

  if (error) {
    return (
      <div className="mx-auto flex min-h-dvh max-w-sm flex-col items-center justify-center gap-4 px-6 text-center">
        <p className="text-fog">{error}</p>
        <Link to="/" className="rounded-xl bg-riser px-5 py-2.5 text-stub">
          Back to the start
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto min-h-dvh max-w-sm px-6 pb-28 pt-6">
      <header className="mb-6">
        <Link to="/" className="text-lg font-bold tracking-tight text-spool">
          decide
        </Link>
      </header>

      {session && (
        <>
          <JoinCodeBadge code={session.join_code} />

          <section className="mt-6">
            <h2 className="text-sm font-semibold text-stub/80">Who's in</h2>
            <ul className="mt-2 space-y-2">
              {session.participants.map((participant) => (
                <li
                  key={participant.id}
                  className="flex items-center justify-between rounded-xl bg-riser px-4 py-3 text-sm"
                >
                  <span className="text-stub/90">
                    {participant.display_name}
                    {participant.id === myPid && (
                      <span className="ml-2 text-xs text-fog">(you)</span>
                    )}
                  </span>
                  {participant.id === session.participants[0]?.id && (
                    <span className="text-xs uppercase tracking-wide text-fog/70">
                      host
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </section>

          <section className="mt-6 rounded-xl bg-riser px-4 py-3 text-sm text-fog">
            <span className="type-mono text-stub/90">{session.deck_size}</span> films ·{" "}
            {describeFilters(session.filters)}
          </section>

          <p className="mt-4 text-xs text-fog/70">
            No need to wait for each other — everyone swipes the same deck in the
            same order, whenever suits. Matches land the moment you agree.
          </p>

          <div className="fixed inset-x-0 bottom-0 bg-gradient-to-t from-house via-house/95 to-transparent px-6 pb-6 pt-8">
            <button
              onClick={() => navigate(`/session/${sessionId}/swipe`)}
              className="mx-auto block w-full max-w-sm rounded-2xl bg-bulb py-4 font-semibold text-press transition-transform active:scale-[0.98]"
            >
              Start swiping
            </button>
          </div>
        </>
      )}
    </div>
  );
}
