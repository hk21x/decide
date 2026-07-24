import { AnimatePresence } from "framer-motion";

import type { DeckItem } from "../lib/types";
import { SwipeCard } from "./SwipeCard";

interface Props {
  items: DeckItem[]; // the next (up to) 3 cards, [0] on top
  lastDirection: 0 | 1; // drives the exit vector of the departing card
  onCommit: (direction: 0 | 1) => void;
  onOpenDetail: (item: DeckItem) => void;
}

/** Exactly three cards rendered (brief §6): top interactive, two behind at
 * scale .95/.90, y +8/+16, pointer-events none. */
export function CardStack({ items, lastDirection, onCommit, onOpenDetail }: Props) {
  return (
    <div
      className="relative mx-auto w-full max-w-sm"
      style={{ aspectRatio: "2 / 3", maxHeight: "62dvh", touchAction: "none" }}
    >
      <AnimatePresence custom={lastDirection} initial={false}>
        {items.slice(0, 3).map((item, i) => (
          <SwipeCard
            key={item.id}
            item={item}
            stackIndex={i}
            onCommit={onCommit}
            onOpenDetail={onOpenDetail}
          />
        ))}
      </AnimatePresence>
    </div>
  );
}
