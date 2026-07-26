import {
  motion,
  useMotionValue,
  useMotionValueEvent,
  useReducedMotion,
  useTransform,
  type PanInfo,
} from "framer-motion";
import { useState } from "react";

import { formatCert, formatRating, formatRuntime } from "../lib/format";
import type { DeckItem } from "../lib/types";
import { PosterImg } from "./PosterImg";
import { StampOverlay } from "./StampOverlay";

const COMMIT_VELOCITY = 500;

function commitPx(): number {
  return window.innerWidth * 0.25;
}

interface Props {
  item: DeckItem;
  stackIndex: number; // 0 = top (interactive), 1-2 behind
  onCommit: (direction: 0 | 1) => void;
  onOpenDetail: (item: DeckItem) => void;
}

export function SwipeCard({ item, stackIndex, onCommit, onOpenDetail }: Props) {
  const reduced = useReducedMotion();
  const x = useMotionValue(0);
  const rotate = useTransform(x, [-200, 200], [-12, 12]);
  const tonightBase = useTransform(x, [40, commitPx()], [0, 0.65]);
  const notTonightBase = useTransform(x, [-commitPx(), -40], [0.65, 0]);
  // -1 = past left threshold, 1 = past right, 0 = neither
  const [armed, setArmed] = useState<-1 | 0 | 1>(0);

  useMotionValueEvent(x, "change", (latest) => {
    const next = latest >= commitPx() ? 1 : latest <= -commitPx() ? -1 : 0;
    if (next !== armed) setArmed(next);
  });

  const isTop = stackIndex === 0;

  function handleDragEnd(_event: unknown, info: PanInfo) {
    const { offset, velocity } = info;
    if (offset.x > commitPx() || velocity.x > COMMIT_VELOCITY) {
      onCommit(1);
    } else if (offset.x < -commitPx() || velocity.x < -COMMIT_VELOCITY) {
      onCommit(0);
    }
    // otherwise dragSnapToOrigin springs the card back
  }

  const runtime = formatRuntime(item.runtime_min);
  const cert = formatCert(item.content_rating);
  const rating = formatRating(item.audience_rating);

  return (
    <motion.div
      className={`swipe-surface absolute inset-0 overflow-hidden rounded-2xl bg-riser shadow-[0_12px_40px_rgba(0,0,0,0.45)] ${
        isTop ? "cursor-grab active:cursor-grabbing" : "pointer-events-none"
      }`}
      style={
        isTop
          ? // touchAction inline as well: Framer sets pan-y on drag="x"
            // elements, which hands diagonal swipes back to iOS scrolling.
            { x, rotate, transformOrigin: "bottom center", zIndex: 3, touchAction: "none" }
          : { zIndex: 3 - stackIndex }
      }
      animate={{ scale: 1 - stackIndex * 0.05, y: stackIndex * 8 }}
      transition={{ type: "spring", stiffness: 320, damping: 28 }}
      drag={isTop ? "x" : false}
      dragSnapToOrigin
      dragElastic={0.9}
      onDragEnd={isTop ? handleDragEnd : undefined}
      variants={{
        exit: (direction: 0 | 1) =>
          reduced
            ? { opacity: 0, transition: { duration: 0.18 } }
            : {
                x: direction === 1 ? window.innerWidth * 1.1 : -window.innerWidth * 1.1,
                rotate: direction === 1 ? 16 : -16,
                transition: { duration: 0.28, ease: [0.32, 0.72, 0.35, 1] },
              },
      }}
      exit="exit"
    >
      <PosterImg itemId={item.id} title={item.title} eager={stackIndex < 2} className="absolute inset-0" />

      {/* bottom scrim with title + facts — pinned colours: this sits on
          the poster, so it must not follow the page theme */}
      <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-[#0D0916F2] via-[#0D091699] to-transparent px-4 pb-4 pr-16 pt-16">
        <h2 className="type-display text-xl text-[#F2EEE6] [display:-webkit-box] [-webkit-box-orient:vertical] [-webkit-line-clamp:2] overflow-hidden">
          {item.title}
        </h2>
        <div className="mt-1.5 flex items-center gap-2 text-xs text-[#B7AECB]">
          {item.year && <span>{item.year}</span>}
          {item.media_type === "show" && (
            <span className="rounded bg-[#8B6CD9]/30 px-1.5 py-px text-[10px] font-semibold uppercase tracking-wide text-[#C9B8F0]">
              Series{item.seasons ? ` · ${item.seasons}` : ""}
            </span>
          )}
          {runtime && <span className="type-mono">{runtime}</span>}
          {cert && (
            <span className="rounded border border-[#4A4160] px-1 py-px text-[10px] leading-tight">
              {cert}
            </span>
          )}
          {rating && <span className="type-mono text-[#F2637A]">★ {rating}</span>}
        </div>
      </div>

      {/* Details are explicit-only: this button, never a card tap — a tap
         was too easy to trigger while lining up a swipe. Pointer events stop
         here so a press on the button can never start a drag. */}
      {isTop && (
        <button
          onPointerDown={(event) => event.stopPropagation()}
          onClick={() => onOpenDetail(item)}
          aria-label={`About ${item.title}`}
          className="absolute bottom-4 right-4 z-10 grid h-11 w-11 place-items-center rounded-full bg-ink/60 text-[#EFE9DF] backdrop-blur-sm active:scale-95"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden>
            <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2" />
            <path d="M12 11v5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            <circle cx="12" cy="7.5" r="1.25" fill="currentColor" />
          </svg>
        </button>
      )}

      {isTop && (
        <>
          <StampOverlay
            label="Tonight"
            side="left"
            baseOpacity={tonightBase}
            armed={armed === 1}
          />
          <StampOverlay
            label="Not tonight"
            side="right"
            baseOpacity={notTonightBase}
            armed={armed === -1}
          />
        </>
      )}
    </motion.div>
  );
}
