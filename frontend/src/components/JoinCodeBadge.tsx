import { QRCodeSVG } from "qrcode.react";
import { useEffect, useState } from "react";

import { api } from "../lib/api";

interface Props {
  code: string;
}

type Tab = "local" | "remote";

/** Join code + QR. With access addresses configured (Settings → Access),
 * two QRs are offered: one for people on the same Wi-Fi, one for remote
 * friends on your tailnet or reverse proxy. Unconfigured, the QR encodes
 * this browser's own origin, exactly as before. */
export function JoinCodeBadge({ code }: Props) {
  const [copied, setCopied] = useState(false);
  const [urls, setUrls] = useState<{ local: string; remote: string | null }>({
    local: window.location.origin,
    remote: null,
  });
  const [tab, setTab] = useState<Tab>("local");

  useEffect(() => {
    api
      .accessConfig()
      .then((access) =>
        setUrls({
          local: access.local_url ?? window.location.origin,
          remote: access.remote_url,
        }),
      )
      .catch(() => {});
  }, []);

  const activeBase = tab === "remote" && urls.remote ? urls.remote : urls.local;
  const joinUrl = `${activeBase}/join/${code}`;

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

      {urls.remote && (
        <div className="flex w-full gap-1 rounded-xl bg-house p-1" role="tablist">
          {(
            [
              ["local", "🏠 Same Wi-Fi"],
              ["remote", "🌍 Anywhere"],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              role="tab"
              aria-selected={tab === key}
              onClick={() => setTab(key)}
              className={`flex-1 rounded-lg py-1.5 text-xs font-semibold ${
                tab === key ? "bg-riser text-stub" : "text-fog"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      )}

      <div className="rounded-xl bg-[#EFE9DF] p-3">
        <QRCodeSVG value={joinUrl} size={140} bgColor="#EFE9DF" fgColor="#0D0916" />
      </div>
      <p className="type-mono max-w-full truncate text-[10px] text-fog/60">{joinUrl}</p>
      <button onClick={copy} className="text-sm font-semibold text-spool">
        {copied ? "Copied" : "Copy join link"}
      </button>
    </div>
  );
}
