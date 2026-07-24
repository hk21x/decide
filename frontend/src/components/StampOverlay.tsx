import { motion, type MotionValue } from "framer-motion";

interface Props {
  label: "Tonight" | "Not tonight";
  side: "left" | "right";
  baseOpacity: MotionValue<number>;
  armed: boolean;
}

/** The overlay stamp. Fades in gently with drag, then SNAPS to full
 * strength at the commit threshold (brief §6 — the visual stand-in for the
 * haptic tick iOS Safari can't give us). */
export function StampOverlay({ label, side, baseOpacity, armed }: Props) {
  const isTonight = label === "Tonight";
  const colour = isTonight ? "border-bulb text-bulb" : "border-seat text-seat";
  const position = side === "left" ? "left-4 -rotate-12" : "right-4 rotate-12";

  return (
    <div className={`pointer-events-none absolute top-6 ${position}`}>
      {/* pre-threshold: proportional, capped well below full strength */}
      <motion.div
        style={{ opacity: baseOpacity }}
        className={`type-display rounded border-[3px] px-3 py-1 text-lg uppercase tracking-wide ${colour} ${
          armed ? "invisible" : ""
        }`}
      >
        {label}
      </motion.div>
      {/* at threshold: the decisive snap */}
      {armed && (
        <motion.div
          initial={{ scale: 1.25, opacity: 0.6 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ type: "spring", stiffness: 900, damping: 30 }}
          className={`type-display absolute inset-0 flex items-center justify-center rounded border-[3px] px-3 py-1 text-lg uppercase tracking-wide ${colour} ${
            isTonight ? "bg-bulb/15" : "bg-seat/15"
          }`}
        >
          {label}
        </motion.div>
      )}
    </div>
  );
}
