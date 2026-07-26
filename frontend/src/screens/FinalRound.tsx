import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { PosterImg } from "../components/PosterImg";
import { api } from "../lib/api";
import { formatMeta } from "../lib/format";
import { openInPlex } from "../lib/plexLink";
import type { DeckItem, PlayerEntry } from "../lib/types";
import { sessionSocket } from "../lib/ws";

/** Seeded Fisher–Yates: every device dealing this session's Final Round
 * sees the same bracket in the same order (FNV-1a hash + mulberry32). */
function seededShuffle<T>(items: T[], seed: string): T[] {
  let h = 2166136261 >>> 0;
  for (let i = 0; i < seed.length; i++) {
    h ^= seed.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  const rand = () => {
    h = (h + 0x6d2b79f5) >>> 0;
    let t = h;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  const out = [...items];
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(rand() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

const HEARTBEAT_MS = 10_000;

type Role = "loading" | "runner" | "spectator";

/** The Final Round runs on ONE device — the runner holds a heartbeat lock,
 * the bracket order is seeded by the session id, and the crown broadcasts,
 * so every phone agrees on both the duels and the verdict. */
export function FinalRoundScreen() {
  const { sessionId = "" } = useParams();
  const navigate = useNavigate();
  const reduced = useReducedMotion();
  const socket = useMemo(() => sessionSocket(sessionId), [sessionId]);

  const [role, setRole] = useState<Role>("loading");
  const [holderName, setHolderName] = useState<string | null>(null);
  const [round, setRound] = useState<DeckItem[]>([]);
  const [winners, setWinners] = useState<DeckItem[]>([]);
  const [duelIndex, setDuelIndex] = useState(0);
  const [champion, setChampion] = useState<DeckItem | null>(null);
  const [machineId, setMachineId] = useState<string | null>(null);
  const [players, setPlayers] = useState<PlayerEntry[]>([]);
  const [playerChoice, setPlayerChoice] = useState<string>("");
  const [note, setNote] = useState<string | null>(null);
  const [kept, setKept] = useState(false);
  const allItems = useRef<Map<string, DeckItem>>(new Map());
  const roleRef = useRef<Role>("loading");
  roleRef.current = role;

  const crownById = useCallback((itemId: string) => {
    const item = allItems.current.get(itemId);
    if (item) setChampion(item);
  }, []);

  // Initial load: matches (everyone needs them to resolve the champion),
  // then either the runner's bracket or the spectator's couch.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const [m, summary] = await Promise.all([
        api.matches(sessionId),
        api.sessionSummary(sessionId),
      ]);
      if (cancelled) return;
      const items = m.matches.map((entry) => entry.item);
      allItems.current = new Map(items.map((item) => [item.id, item]));

      if (summary.crowned_item_id) {
        crownById(summary.crowned_item_id); // verdict already in
        return;
      }
      if (items.length < 2) {
        navigate(`/session/${sessionId}/matches`, { replace: true });
        return;
      }
      const claim = await api.claimFinal(sessionId);
      if (cancelled) return;
      if (claim.mine) {
        setRound(seededShuffle(items, sessionId));
        setRole("runner");
      } else {
        setHolderName(claim.holder_name);
        setRole("spectator");
      }
    })().catch(() => setNote("Couldn't load the Final Round."));
    return () => {
      cancelled = true;
    };
  }, [sessionId, navigate, crownById]);

  useEffect(() => {
    api.setupStatus().then((s) => setMachineId(s.machine_id)).catch(() => {});
    api
      .players()
      .then((p) => {
        setPlayers(p.players);
        if (p.players.length === 1) setPlayerChoice(p.players[0].id);
      })
      .catch(() => {});
  }, []);

  // Live events: the crown ends it for everyone; lock churn updates the couch.
  useEffect(() => {
    const off = socket.subscribe((event) => {
      if (event.type === "crowned") {
        crownById(event.item_id as string);
      } else if (event.type === "final_started" && roleRef.current === "spectator") {
        setHolderName(event.display_name as string);
      } else if (event.type === "final_released" && roleRef.current === "spectator") {
        // Runner walked away — try to take over.
        void api.claimFinal(sessionId).then((claim) => {
          if (claim.mine) {
            const items = [...allItems.current.values()];
            setRound(seededShuffle(items, sessionId));
            setWinners([]);
            setDuelIndex(0);
            setRole("runner");
          } else {
            setHolderName(claim.holder_name);
          }
        });
      }
    });
    return off;
  }, [socket, sessionId, crownById]);

  // Runner keeps the lock warm; releases it on the way out (unless crowned —
  // the server already cleared it).
  useEffect(() => {
    if (role !== "runner") return;
    const timer = setInterval(() => void api.claimFinal(sessionId), HEARTBEAT_MS);
    return () => {
      clearInterval(timer);
      if (!champion) void api.releaseFinal(sessionId).catch(() => {});
    };
  }, [role, sessionId, champion]);

  const duel = useMemo(() => {
    const a = round[duelIndex * 2];
    const b = round[duelIndex * 2 + 1];
    return a && b ? ([a, b] as const) : null;
  }, [round, duelIndex]);

  const bye = round.length % 2 === 1 ? round[round.length - 1] : null;
  const roundLabel = round.length <= 2 ? "The Final" : `Round of ${round.length}`;

  async function pick(winner: DeckItem) {
    const nextWinners = [...winners, winner];
    const duelsInRound = Math.floor(round.length / 2);
    if (duelIndex + 1 < duelsInRound) {
      setWinners(nextWinners);
      setDuelIndex(duelIndex + 1);
      return;
    }
    const survivors = bye ? [...nextWinners, bye] : nextWinners;
    if (survivors.length === 1) {
      setChampion(survivors[0]);
      try {
        await api.crown(sessionId, survivors[0].id);
      } catch {
        /* crowning is best-effort; the champion screen still shows */
      }
      return;
    }
    setRound(survivors);
    setWinners([]);
    setDuelIndex(0);
  }

  async function keepChampion() {
    if (!champion) return;
    try {
      await api.saveToAlbum(sessionId, champion.id, true);
      setKept(true);
    } catch {
      setNote("Couldn't save the stub just now.");
    }
  }

  async function sendToPlayer() {
    if (!champion || !playerChoice) return;
    try {
      await api.playOn(champion.id, playerChoice);
      const name = players.find((p) => p.id === playerChoice)?.name ?? "the player";
      setNote(`Sent to ${name}. Enjoy the film.`);
    } catch (err) {
      setNote(
        err instanceof Error
          ? err.message
          : "Couldn't reach that player. Check Plex is open on it.",
      );
    }
  }

  if (champion) {
    return (
      <div className="mx-auto flex min-h-dvh max-w-sm flex-col items-center justify-center px-6 py-10 text-center">
        <motion.div
          initial={reduced ? { opacity: 0 } : { scale: 0.92, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ type: "spring", stiffness: 260, damping: 24 }}
          className="w-full"
        >
          <p className="type-mono text-xs uppercase tracking-[0.3em] text-bulb">
            👑 Tonight's {champion.media_type === "show" ? "series" : "film"}
          </p>
          <div className="mx-auto mt-4 w-56">
            <PosterImg
              itemId={champion.id}
              title={champion.title}
              eager
              className="rounded-2xl shadow-[0_16px_48px_rgba(0,0,0,0.5)]"
            />
          </div>
          <h1 className="type-display mt-5 text-2xl text-stub">{champion.title}</h1>
          <p className="type-mono mt-1 text-sm text-fog">{formatMeta(champion)}</p>

          <div className="mt-8 flex w-full flex-col gap-3">
            {machineId && (
              <button
                onClick={() => openInPlex(champion.id, machineId, champion.media_type)}
                className="rounded-2xl bg-bulb py-4 font-semibold text-press"
              >
                Open in Plex
              </button>
            )}
            {players.length > 0 && (
              <div className="flex gap-2">
                {players.length > 1 && (
                  <select
                    value={playerChoice}
                    onChange={(e) => setPlayerChoice(e.target.value)}
                    aria-label="Pick a player"
                    className="flex-1 rounded-2xl border border-hairline bg-riser px-3 text-sm text-stub"
                  >
                    <option value="">Pick a screen…</option>
                    {players.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name}
                      </option>
                    ))}
                  </select>
                )}
                <button
                  onClick={sendToPlayer}
                  disabled={!playerChoice}
                  className="flex-1 rounded-2xl border-2 border-spool py-3.5 font-semibold text-spool disabled:opacity-40"
                >
                  Play on {players.length === 1 ? players[0].name : "the TV"}
                </button>
              </div>
            )}
            <button
              onClick={keepChampion}
              disabled={kept}
              className="rounded-2xl border border-hairline py-3.5 font-semibold text-fog disabled:opacity-60"
            >
              {kept ? "Stub kept ✓" : "Keep the stub"}
            </button>
            <Link
              to={`/session/${sessionId}/matches`}
              className="mt-1 text-sm text-fog"
            >
              Back to matches
            </Link>
          </div>
          {note && <p className="mt-4 text-sm text-spool">{note}</p>}
        </motion.div>
      </div>
    );
  }

  if (role === "spectator") {
    return (
      <div className="mx-auto flex min-h-dvh max-w-sm flex-col items-center justify-center px-6 text-center">
        <p className="text-4xl" aria-hidden>
          🍿
        </p>
        <h1 className="type-display mt-4 text-xl text-stub">
          {holderName ?? "Someone"} is running the Final Round
        </h1>
        <p className="mt-2 text-sm text-fog">
          One phone, everyone arguing at it — that's the rules. The verdict
          lands here the moment it's crowned.
        </p>
        <Link
          to={`/session/${sessionId}/matches`}
          className="mt-8 text-sm font-semibold text-spool"
        >
          Back to matches
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto flex min-h-dvh max-w-sm flex-col px-5 pb-10 pt-6">
      <header className="mb-4 flex items-baseline justify-between">
        <Link
          to={`/session/${sessionId}/matches`}
          className="text-sm font-semibold text-spool"
        >
          ‹ Matches
        </Link>
        <span className="type-mono text-xs uppercase tracking-[0.25em] text-fog">
          {role === "loading" ? "…" : roundLabel}
        </span>
      </header>

      <h1 className="type-display text-xl text-stub">Which one wins?</h1>
      <p className="mt-1 text-sm text-fog">
        Pass the phone round, argue it out, tap the winner.
      </p>
      {note && <p className="mt-2 text-sm text-bulb">{note}</p>}

      <AnimatePresence mode="wait">
        {duel && (
          <motion.div
            key={`${duel[0].id}-${duel[1].id}`}
            initial={reduced ? { opacity: 0 } : { opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.22 }}
            className="mt-5 flex flex-1 flex-col gap-3"
          >
            {duel.map((item, i) => (
              <button
                key={item.id}
                onClick={() => pick(item)}
                className="flex flex-1 items-center gap-4 rounded-2xl bg-riser p-3 text-left transition-transform active:scale-[0.98]"
              >
                <PosterImg
                  itemId={item.id}
                  title={item.title}
                  eager
                  className="w-24 shrink-0 rounded-lg"
                />
                <div className="min-w-0">
                  {i === 1 && (
                    <p className="type-mono mb-1 text-[10px] uppercase tracking-[0.25em] text-fog/60">
                      versus
                    </p>
                  )}
                  <p className="type-display text-lg text-stub">{item.title}</p>
                  <p className="type-mono mt-1 text-xs text-fog">{formatMeta(item)}</p>
                </div>
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>

      {bye && duel && (
        <p className="type-mono mt-3 text-center text-xs text-fog/60">
          {bye.title} sits this one out and meets the winner.
        </p>
      )}
    </div>
  );
}
