import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { CardStack } from "../components/CardStack";
import { DetailSheet } from "../components/DetailSheet";
import { api, posterUrl } from "../lib/api";
import { SwipeQueue } from "../lib/swipeQueue";
import type { DeckItem } from "../lib/types";
import { sessionSocket } from "../lib/ws";

interface UndoState {
  item: DeckItem;
  direction: 0 | 1;
}

export function DeckScreen() {
  const { sessionId = "" } = useParams();
  const navigate = useNavigate();

  const [items, setItems] = useState<DeckItem[] | null>(null);
  const [index, setIndex] = useState(0);
  const [lastDirection, setLastDirection] = useState<0 | 1>(1);
  const [sheetItem, setSheetItem] = useState<DeckItem | null>(null);
  const [undo, setUndo] = useState<UndoState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [matchCount, setMatchCount] = useState(0);
  const [matchToast, setMatchToast] = useState<string | null>(null);

  const undoTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastCommitAt = useRef(0);
  const itemsRef = useRef<DeckItem[] | null>(null);
  const queue = useMemo(() => new SwipeQueue(sessionId), [sessionId]);
  const socket = useMemo(() => sessionSocket(sessionId), [sessionId]);

  useEffect(() => () => queue.destroy(), [queue]);

  // Live events: a match prints a toast (never steals the gesture — it's
  // purely visual, pointer events pass straight through it).
  useEffect(() => {
    const off = socket.subscribe((event) => {
      if (event.type === "match") {
        setMatchCount((count) => count + 1);
        const item = itemsRef.current?.find((i) => i.id === event.item_id);
        if (item) {
          setMatchToast(item.title);
          if (toastTimer.current) clearTimeout(toastTimer.current);
          toastTimer.current = setTimeout(() => setMatchToast(null), 3500);
        }
      } else if (event.type === "unmatch") {
        setMatchCount((count) => Math.max(0, count - 1));
      }
    });
    return off;
  }, [socket]);

  // Load the frozen deck; resume where this participant left off.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [deck, progress] = await Promise.all([
          api.deck(sessionId),
          api.progress(sessionId),
        ]);
        if (cancelled) return;
        setItems(deck.items);
        itemsRef.current = deck.items;
        setMatchCount(progress.match_count);
        const mine = progress.participants[0];
        if (mine && mine.swiped > 0) setIndex(Math.min(mine.swiped, deck.items.length));
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Couldn't load the deck.");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  // Scroll-lock the document while the deck is up: there is nothing to
  // scroll here, and iOS otherwise rubber-bands the page and eats swipes.
  useEffect(() => {
    const html = document.documentElement;
    const previous = { html: html.style.overflow, body: document.body.style.overflow };
    html.style.overflow = "hidden";
    document.body.style.overflow = "hidden";
    return () => {
      html.style.overflow = previous.html;
      document.body.style.overflow = previous.body;
    };
  }, []);

  // Preload the next few posters so promotion never shows a blank card.
  useEffect(() => {
    if (!items) return;
    for (const item of items.slice(index + 1, index + 4)) {
      const img = new Image();
      img.src = posterUrl(item.id);
    }
  }, [items, index]);

  const top: DeckItem | undefined = items?.[index];
  const finished = items !== null && index >= items.length;

  const commit = useCallback(
    (direction: 0 | 1) => {
      // The single commit path (C4): drag release, buttons, arrow keys and
      // the detail sheet all land here.
      const now = performance.now();
      if (now - lastCommitAt.current < 200) return; // mid-exit guard
      const current = items?.[index];
      if (!current || sheetItem) return;
      lastCommitAt.current = now;

      setLastDirection(direction);
      queue.add(current.id, direction);
      setIndex((i) => i + 1);

      if (undoTimer.current) clearTimeout(undoTimer.current);
      setUndo({ item: current, direction });
      undoTimer.current = setTimeout(() => setUndo(null), 5000);
    },
    [items, index, sheetItem, queue],
  );

  const commitFromSheet = useCallback(
    (direction: 0 | 1) => {
      setSheetItem(null);
      // Sheet commit bypasses the sheet-open guard by deferring a tick.
      setTimeout(() => {
        const current = items?.[index];
        if (!current) return;
        setLastDirection(direction);
        queue.add(current.id, direction);
        setIndex((i) => i + 1);
        if (undoTimer.current) clearTimeout(undoTimer.current);
        setUndo({ item: current, direction });
        undoTimer.current = setTimeout(() => setUndo(null), 5000);
      }, 0);
    },
    [items, index, queue],
  );

  const handleUndo = useCallback(() => {
    if (!undo) return;
    const { item } = undo;
    setUndo(null);
    if (undoTimer.current) clearTimeout(undoTimer.current);
    if (!queue.removePending(item.id)) {
      void api.undoSwipe(sessionId, item.id).catch(() => {
        /* the swipe stays on the server; not worth blocking the deck */
      });
    }
    setIndex((i) => Math.max(0, i - 1));
  }, [undo, queue, sessionId]);

  // Keyboard: arrows swipe, Z undoes (C4 — same code path as the buttons).
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (sheetItem) return; // sheet handles Escape itself
      if (event.key === "ArrowRight") commit(1);
      else if (event.key === "ArrowLeft") commit(0);
      else if (event.key.toLowerCase() === "z") handleUndo();
      else if (event.key === "ArrowUp" || event.key.toLowerCase() === "i") {
        const current = items?.[index];
        if (current) setSheetItem(current);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [commit, handleUndo, sheetItem, items, index]);

  // Deck finished: flush the queue, then over to the matches.
  useEffect(() => {
    if (!finished) return;
    void queue.flush().then(() => navigate(`/session/${sessionId}/matches`));
  }, [finished, queue, navigate, sessionId]);

  if (error) {
    return (
      <div className="mx-auto flex min-h-dvh max-w-sm flex-col items-center justify-center gap-4 px-6 text-center">
        <p className="text-fog">{error}</p>
        <button
          onClick={() => navigate("/")}
          className="rounded-xl bg-riser px-5 py-2.5 text-stub"
        >
          Back to the start
        </button>
      </div>
    );
  }

  return (
    <div className="mx-auto flex h-dvh max-w-lg flex-col overflow-hidden px-4 pb-6 pt-4">
      <header className="mb-4 flex items-baseline justify-between">
        <span className="text-lg font-bold tracking-tight text-spool">decide</span>
        <div className="flex items-baseline gap-4">
          {matchCount > 0 && (
            <Link
              to={`/session/${sessionId}/matches`}
              className="type-mono text-sm text-bulb"
              aria-label={`${matchCount} matches so far`}
            >
              🎟 {matchCount}
            </Link>
          )}
          {items && (
            <span className="type-mono text-sm text-fog" aria-label="Progress">
              {Math.min(index, items.length)} / {items.length}
            </span>
          )}
        </div>
      </header>

      <AnimatePresence>
        {matchToast && (
          <motion.div
            initial={{ y: -24, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: -24, opacity: 0 }}
            transition={{ duration: 0.25 }}
            className="pointer-events-none fixed inset-x-0 top-4 z-40 flex justify-center"
            role="status"
          >
            <div className="type-mono rounded-full bg-[#EFE9DF] px-5 py-2 text-sm font-bold text-ink shadow-lg">
              🎟 It's a match — {matchToast}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <main className="flex flex-1 flex-col justify-center">
        {items === null ? (
          <div
            className="mx-auto w-full max-w-sm animate-pulse rounded-2xl bg-riser"
            style={{ aspectRatio: "2 / 3", maxHeight: "62dvh" }}
          />
        ) : finished ? (
          <p className="text-center text-fog">Wrapping up…</p>
        ) : (
          <CardStack
            items={items.slice(index, index + 3)}
            lastDirection={lastDirection}
            onCommit={commit}
            onOpenDetail={setSheetItem}
          />
        )}

        <div className="relative mt-6">
          {undo && (
            <button
              onClick={handleUndo}
              className="absolute -top-12 left-1/2 flex -translate-x-1/2 items-center gap-2 rounded-full bg-riser px-4 py-1.5 text-sm text-stub shadow-lg"
            >
              <span aria-hidden>↩</span> Undo
              <span className="max-w-40 truncate text-fog">{undo.item.title}</span>
            </button>
          )}
          <div className="flex items-center justify-center gap-4">
            <button
              onClick={() => commit(0)}
              disabled={!top}
              className="flex-1 max-w-44 rounded-2xl border-2 border-seat py-3.5 font-semibold text-seat transition-transform active:scale-95 disabled:opacity-40"
            >
              Not tonight
            </button>
            <button
              onClick={() => commit(1)}
              disabled={!top}
              className="flex-1 max-w-44 rounded-2xl bg-bulb py-3.5 font-semibold text-press transition-transform active:scale-95 disabled:opacity-40"
            >
              Tonight
            </button>
          </div>
        </div>
      </main>

      <DetailSheet
        item={sheetItem}
        onClose={() => setSheetItem(null)}
        onCommit={commitFromSheet}
      />
    </div>
  );
}
