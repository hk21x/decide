import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api, ApiError } from "../lib/api";
import { getName, getPid, recordSession, saveName, savePid } from "../lib/session";
import type { SessionSummary } from "../lib/types";

export function JoinScreen() {
  const navigate = useNavigate();
  const { code: codeParam } = useParams();
  const [code, setCode] = useState((codeParam ?? "").toUpperCase().slice(0, 6));
  const [session, setSession] = useState<SessionSummary | null>(null);
  const [displayName, setDisplayName] = useState(getName());
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Look the code up as soon as six characters are in.
  useEffect(() => {
    setSession(null);
    setError(null);
    if (code.length !== 6) return;
    let cancelled = false;
    api
      .lookupCode(code)
      .then((summary) => {
        if (!cancelled) setSession(summary);
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404) {
          setError("No session with that code. Check it and try again.");
        } else if (err instanceof ApiError && err.status === 410) {
          setError("This session has closed.");
        } else if (err instanceof ApiError && err.status === 429) {
          setError("Too many attempts. Wait a minute, then try again.");
        } else {
          setError("Couldn't reach the server. Check the connection and try again.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [code]);

  const knownPid = session ? getPid(session.id) : null;
  const knownAs = session?.participants.find((p) => p.id === knownPid) ?? null;

  async function rejoin() {
    if (!session || !knownPid) return;
    setBusy(true);
    setError(null);
    try {
      await api.rejoin(session.id, knownPid);
      recordSession({ id: session.id, code: session.join_code, deck_size: session.deck_size });
      navigate(`/session/${session.id}/lobby`);
    } catch {
      setError("Couldn't rejoin — join with your name instead.");
    } finally {
      setBusy(false);
    }
  }

  async function join() {
    if (!session) return;
    const name = displayName.trim();
    if (!name) {
      setError("Add your name so the others know who's swiping.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const joined = await api.join(session.id, name);
      savePid(session.id, joined.participant_id);
      recordSession({ id: session.id, code: session.join_code, deck_size: session.deck_size });
      saveName(name);
      navigate(`/session/${session.id}/lobby`);
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 409
          ? "This session already has four people."
          : err instanceof Error
            ? err.message
            : "Couldn't join the session.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto flex min-h-dvh max-w-sm flex-col justify-center px-6 pb-16">
      <Link to="/" className="mb-8 text-lg font-bold tracking-tight text-spool">
        decide
      </Link>
      <h1 className="type-display text-xl text-stub">Join with a code</h1>
      <p className="mt-1 text-sm text-fog">
        Six characters, from whoever set the session up.
      </p>

      <input
        type="text"
        inputMode="text"
        autoCapitalize="characters"
        autoCorrect="off"
        spellCheck={false}
        value={code}
        maxLength={6}
        onChange={(e) =>
          setCode(e.target.value.toUpperCase().replace(/[^0-9A-Z]/g, ""))
        }
        placeholder="ABC123"
        aria-label="Join code"
        className="type-mono mt-6 w-full rounded-2xl border border-hairline bg-riser px-4 py-4 text-center text-xl tracking-[0.4em] text-stub placeholder:text-fog/40"
      />

      {error && <p className="mt-4 text-sm text-bulb">{error}</p>}

      {session && (
        <div className="mt-6 rounded-2xl bg-riser p-5">
          {knownAs && (
            <button
              onClick={rejoin}
              disabled={busy}
              className="mb-4 w-full rounded-xl border-2 border-spool py-3 font-semibold text-spool disabled:opacity-40"
            >
              Rejoin as {knownAs.display_name}
            </button>
          )}
          <p className="text-sm text-stub/90">
            {session.participants[0]?.display_name ?? "Someone"}'s session ·{" "}
            <span className="type-mono">{session.deck_size}</span> films
          </p>
          <p className="mt-1 text-xs text-fog">
            {session.participants.length} of 4 people in so far
          </p>
          <input
            type="text"
            value={displayName}
            maxLength={40}
            onChange={(e) => setDisplayName(e.target.value)}
            placeholder="Your name"
            className="mt-4 w-full rounded-xl border border-hairline bg-house px-4 py-3 text-stub placeholder:text-fog/50"
          />
          <button
            onClick={join}
            disabled={busy}
            className="mt-4 w-full rounded-2xl bg-bulb py-3.5 font-semibold text-press transition-transform active:scale-[0.98] disabled:opacity-40"
          >
            {busy ? "Joining…" : "Join the session"}
          </button>
        </div>
      )}
    </div>
  );
}
