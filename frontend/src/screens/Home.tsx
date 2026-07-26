import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api, ApiError } from "../lib/api";
import { dropSession, getPid, listSessions } from "../lib/session";
import type { LibraryStatus, ProgressResponse } from "../lib/types";

interface RecentView {
  id: string;
  code: string;
  myName: string;
  swiped: number;
  total: number;
  matches: number;
  done: boolean;
}

export function HomeScreen() {
  const navigate = useNavigate();
  const [status, setStatus] = useState<LibraryStatus | null>(null);
  const [recents, setRecents] = useState<RecentView[]>([]);

  // Recent sessions (brief §7 Home). A 401 means this browser lost its
  // cookie (or switched origin) — rejoin with the stored participant id
  // rather than burning one of the four seats.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const views: RecentView[] = [];
      for (const record of listSessions()) {
        const pid = getPid(record.id);
        let progress: ProgressResponse | null = null;
        try {
          progress = await api.progress(record.id);
        } catch (err) {
          if (err instanceof ApiError && err.status === 401 && pid) {
            try {
              await api.rejoin(record.id, pid);
              progress = await api.progress(record.id);
            } catch {
              /* fall through to cleanup below */
            }
          } else if (
            err instanceof ApiError &&
            (err.status === 404 || err.status === 410)
          ) {
            dropSession(record.id);
            continue;
          }
        }
        if (!progress) continue;
        const mine = progress.participants.find((p) => p.participant_id === pid);
        if (!mine) continue;
        views.push({
          id: record.id,
          code: record.code,
          myName: mine.display_name,
          swiped: mine.swiped,
          total: mine.total,
          matches: progress.match_count,
          done: mine.swiped >= mine.total,
        });
      }
      if (!cancelled) setRecents(views);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    api
      .libraryStatus()
      .then((library) => {
        // Fresh install (or signed out): straight into the wizard.
        if (library.stage !== "ready" || library.item_count === 0) {
          navigate("/setup", { replace: true });
        } else {
          setStatus(library);
        }
      })
      .catch(() => setStatus(null));
  }, [navigate]);

  return (
    <div className="mx-auto flex min-h-dvh max-w-sm flex-col justify-center px-6 pb-16">
      <Link
        to="/settings"
        aria-label="Settings"
        className="fixed right-5 top-5 grid h-10 w-10 place-items-center rounded-full bg-riser text-fog"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
          <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="2" />
          <path
            d="M12 2v3m0 14v3M2 12h3m14 0h3M4.9 4.9l2.1 2.1m10 10 2.1 2.1M19.1 4.9 17 7m-10 10-2.1 2.1"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
          />
        </svg>
      </Link>
      <h1 className="sr-only">decide — Swipe. Decide. Watch.</h1>
      <div className="overflow-hidden rounded-3xl">
        <img
          src="/decide-logo.png"
          alt="decide — a film-reel bow in purple and pink. Swipe. Decide. Watch."
          className="w-full"
          draggable={false}
        />
      </div>
      {status && status.item_count > 0 && (
        <p className="type-mono mt-3 text-center text-xs text-fog/70">
          {status.item_count.toLocaleString("en-GB")} films in the library
        </p>
      )}

      <div className="mt-10 flex flex-col gap-3">
        <Link
          to="/new"
          className="rounded-2xl bg-bulb px-5 py-4 text-center font-semibold text-press transition-transform active:scale-[0.98]"
        >
          Start a session together
        </Link>
        <Link
          to="/join"
          className="rounded-2xl border border-spool px-5 py-4 text-center font-semibold text-spool transition-transform active:scale-[0.98]"
        >
          Join with a code
        </Link>
        <Link
          to="/solo"
          className="rounded-2xl border border-hairline px-5 py-4 text-center font-semibold text-fog transition-transform active:scale-[0.98]"
        >
          Swipe solo
        </Link>
        <Link to="/album" className="mt-2 text-center text-sm text-fog">
          🎟 Stub album
        </Link>
      </div>

      {recents.length > 0 && (
        <section className="mt-8">
          <h2 className="text-xs uppercase tracking-[0.2em] text-fog/70">
            Recent sessions
          </h2>
          <ul className="mt-2 space-y-2">
            {recents.map((recent) => (
              <li key={recent.id}>
                <Link
                  to={
                    recent.done
                      ? `/session/${recent.id}/matches`
                      : `/session/${recent.id}/swipe`
                  }
                  className="flex items-center justify-between rounded-xl bg-riser px-4 py-3 text-sm"
                >
                  <span className="text-stub/90">
                    <span className="type-mono text-xs tracking-[0.15em] text-fog">
                      {recent.code}
                    </span>{" "}
                    · {recent.done ? "finished" : "in progress"}
                  </span>
                  <span className="type-mono text-xs text-fog">
                    {recent.swiped}/{recent.total}
                    {recent.matches > 0 && (
                      <span className="ml-2 text-bulb">🎟 {recent.matches}</span>
                    )}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
