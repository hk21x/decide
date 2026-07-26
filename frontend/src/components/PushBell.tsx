import { useEffect, useState } from "react";

import { enablePush, isSubscribed, pushSupported } from "../lib/push";

/** "Get match alerts" — shown only where push can actually work. */
export function PushBell({ sessionId }: { sessionId: string }) {
  const [state, setState] = useState<"hidden" | "off" | "on" | "error">("hidden");
  const [note, setNote] = useState<string | null>(null);

  useEffect(() => {
    if (!pushSupported()) return;
    void isSubscribed().then((subscribed) => setState(subscribed ? "on" : "off"));
  }, []);

  if (state === "hidden") return null;

  async function enable() {
    try {
      await enablePush(sessionId);
      setState("on");
      setNote(null);
    } catch (err) {
      setState("error");
      setNote(err instanceof Error ? err.message : "Couldn't turn alerts on.");
    }
  }

  return (
    <div className="mt-3">
      <button
        onClick={state === "on" ? undefined : enable}
        disabled={state === "on"}
        className={`w-full rounded-xl border py-2.5 text-sm font-semibold ${
          state === "on"
            ? "border-hairline text-fog/70"
            : "border-spool text-spool"
        }`}
      >
        {state === "on" ? "🔔 Match alerts on" : "🔔 Get match alerts"}
      </button>
      {note && <p className="mt-1.5 text-xs text-bulb">{note}</p>}
    </div>
  );
}
