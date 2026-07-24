import { motion, useReducedMotion } from "framer-motion";

import { formatCert, formatRuntime } from "../lib/format";
import type { MatchEntry } from "../lib/types";

interface Props {
  entry: MatchEntry;
  isNew?: boolean; // freshly matched -> printer-feed animation
  onOpen?: () => void;
}

/** The signature moment (brief §8.4): a match prints a ticket stub — cream
 * stock on the dark ground, perforated edge, Space Mono. It feeds in with a
 * short mechanical slide and settle, never a bounce. */
export function TicketStub({ entry, isNew = false, onOpen }: Props) {
  const reduced = useReducedMotion();
  const runtime = formatRuntime(entry.item.runtime_min);
  const cert = formatCert(entry.item.content_rating);
  const date = new Date(entry.matched_at * 1000).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
  const partial = entry.right_count < entry.participant_count;

  return (
    <motion.li
      initial={isNew && !reduced ? { y: -30, opacity: 0 } : false}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.34, ease: [0.22, 0.9, 0.32, 1] }}
      className="list-none"
    >
      <button
        onClick={onOpen}
        className="type-mono block w-full text-left"
        aria-label={`${entry.item.title} — open in Plex`}
      >
        {/* Ticket stock is a material, not a theme colour — cream in both modes. */}
        <div className="relative rounded-lg bg-[#EFE9DF] px-6 py-4 text-ink shadow-[0_8px_24px_rgba(0,0,0,0.4)]">
          {/* punch holes over the dark ground */}
          <span
            aria-hidden
            className="absolute -left-2.5 top-1/2 h-5 w-5 -translate-y-1/2 rounded-full bg-house"
          />
          <span
            aria-hidden
            className="absolute -right-2.5 top-1/2 h-5 w-5 -translate-y-1/2 rounded-full bg-house"
          />
          <p className="text-[10px] uppercase tracking-[0.25em] text-ink/55">
            Admit {partial ? `${entry.right_count} of ${entry.participant_count}` : "all"}
          </p>
          <p className="mt-1 text-lg font-bold leading-snug">{entry.item.title}</p>
          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-0.5 border-t border-dashed border-ink/30 pt-2 text-xs text-ink/75">
            {entry.item.year && <span>{entry.item.year}</span>}
            {runtime && <span>{runtime}</span>}
            {cert && <span>{cert}</span>}
            <span>{date}</span>
          </div>
          <p className="mt-1.5 text-xs uppercase tracking-wide text-ink/55">
            {entry.right_names.join(" + ")}
          </p>
        </div>
      </button>
    </motion.li>
  );
}
