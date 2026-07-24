import { QRCodeSVG } from "qrcode.react";
import { useState } from "react";

interface Props {
  code: string;
}

/** Join code + QR. The QR encodes this browser's own origin — the only
 * party that knows which hostname humans are actually using. */
export function JoinCodeBadge({ code }: Props) {
  const [copied, setCopied] = useState(false);
  const joinUrl = `${window.location.origin}/join/${code}`;

  async function copy() {
    try {
      await navigator.clipboard.writeText(joinUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard unavailable (plain http on some browsers) — QR still works */
    }
  }

  return (
    <div className="flex flex-col items-center gap-4 rounded-2xl bg-riser px-6 py-6">
      <p className="text-xs uppercase tracking-[0.2em] text-fog">Join code</p>
      <p className="type-mono text-2xl font-bold tracking-[0.35em] text-stub">
        {code}
      </p>
      <div className="rounded-xl bg-[#EFE9DF] p-3">
        <QRCodeSVG value={joinUrl} size={140} bgColor="#EFE9DF" fgColor="#0D0916" />
      </div>
      <button onClick={copy} className="text-sm font-semibold text-spool">
        {copied ? "Copied" : "Copy join link"}
      </button>
    </div>
  );
}
