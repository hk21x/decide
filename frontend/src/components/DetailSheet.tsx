import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useEffect } from "react";

import { backdropUrl, posterUrl } from "../lib/api";
import { formatCert, formatRating, formatRuntime } from "../lib/format";
import type { DeckItem } from "../lib/types";

interface Props {
  item: DeckItem | null;
  onClose: () => void;
  onCommit?: (direction: 0 | 1) => void;
}

export function DetailSheet({ item, onClose, onCommit }: Props) {
  const reduced = useReducedMotion();

  useEffect(() => {
    if (!item) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [item, onClose]);

  const runtime = item ? formatRuntime(item.runtime_min) : null;
  const cert = item ? formatCert(item.content_rating) : null;
  const rating = item ? formatRating(item.audience_rating) : null;

  return (
    <AnimatePresence>
      {item && (
        <motion.div
          className="fixed inset-0 z-50 flex items-end justify-center"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.18 }}
        >
          <button
            aria-label="Close details"
            className="absolute inset-0 bg-ink/70"
            onClick={onClose}
          />
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-label={`${item.title} details`}
            className="relative z-10 max-h-[88dvh] w-full max-w-lg overflow-y-auto rounded-t-2xl bg-riser"
            initial={reduced ? { opacity: 0 } : { y: "100%" }}
            animate={reduced ? { opacity: 1 } : { y: 0 }}
            exit={reduced ? { opacity: 0 } : { y: "100%" }}
            transition={{ type: "spring", stiffness: 380, damping: 38 }}
          >
            <div className="relative aspect-video w-full overflow-hidden">
              <img
                src={item.has_backdrop ? backdropUrl(item.id) : posterUrl(item.id)}
                alt=""
                className="h-full w-full object-cover"
                draggable={false}
              />
              <div className="absolute inset-0 bg-gradient-to-t from-riser via-riser/30 to-transparent" />
              <button
                autoFocus
                onClick={onClose}
                aria-label="Close"
                className="absolute right-3 top-3 grid h-9 w-9 place-items-center rounded-full bg-ink/70 text-[#EFE9DF]"
              >
                ✕
              </button>
            </div>

            <div className="px-5 pb-8 pt-1">
              <h2 className="type-display text-xl text-stub">{item.title}</h2>
              {item.tagline && (
                <p className="mt-1 text-sm italic text-fog">{item.tagline}</p>
              )}
              <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-fog">
                {item.year && <span>{item.year}</span>}
                {item.media_type === "show" && (
                  <span className="rounded-full bg-spool/20 px-2 py-0.5 font-semibold text-spool">
                    Series{item.seasons ? ` · ${item.seasons} seasons` : ""}
                  </span>
                )}
                {runtime && <span className="type-mono">{runtime}</span>}
                {cert && (
                  <span className="rounded border border-hairline px-1 py-px text-[10px]">
                    {cert}
                  </span>
                )}
                {rating && <span className="type-mono text-bulb">★ {rating}</span>}
                {item.genres.slice(0, 3).map((genre) => (
                  <span key={genre} className="rounded-full bg-house px-2 py-0.5">
                    {genre}
                  </span>
                ))}
              </div>

              {item.summary && (
                <p className="mt-4 text-sm leading-relaxed text-stub/90">{item.summary}</p>
              )}

              {item.directors.length > 0 && (
                <p className="mt-4 text-sm text-fog">
                  <span className="text-stub/80">Directed by</span>{" "}
                  {item.directors.join(", ")}
                </p>
              )}

              {item.cast.length > 0 && (
                <div className="mt-3 text-sm text-fog">
                  <span className="text-stub/80">Starring</span>{" "}
                  {item.cast
                    .map((member) =>
                      member.role ? `${member.name} (${member.role})` : member.name,
                    )
                    .join(", ")}
                </div>
              )}

              {onCommit && (
                <div className="mt-6 flex gap-3">
                  <button
                    onClick={() => {
                      onClose();
                      onCommit(0);
                    }}
                    className="flex-1 rounded-xl border-2 border-seat py-3 font-semibold text-seat"
                  >
                    Not tonight
                  </button>
                  <button
                    onClick={() => {
                      onClose();
                      onCommit(1);
                    }}
                    className="flex-1 rounded-xl bg-bulb py-3 font-semibold text-press"
                  >
                    Tonight
                  </button>
                </div>
              )}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
