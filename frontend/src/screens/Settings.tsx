import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api } from "../lib/api";
import { getTheme, setTheme, type Theme } from "../lib/theme";
import type { AccessConfig, CacheStats, LibraryStatus, SetupStatus } from "../lib/types";

function formatBytes(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${bytes} B`;
}

export function SettingsScreen() {
  const navigate = useNavigate();
  const [setup, setSetup] = useState<SetupStatus | null>(null);
  const [library, setLibrary] = useState<LibraryStatus | null>(null);
  const [cache, setCache] = useState<CacheStats | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [theme, setThemeState] = useState<Theme>(getTheme());
  const [access, setAccess] = useState<AccessConfig | null>(null);
  const [localUrl, setLocalUrl] = useState("");
  const [remoteUrl, setRemoteUrl] = useState("");
  const [accessNote, setAccessNote] = useState<string | null>(null);

  function pickTheme(next: Theme) {
    setThemeState(next);
    setTheme(next);
  }

  const refresh = useCallback(() => {
    api.setupStatus().then(setSetup).catch(() => {});
    api.libraryStatus().then(setLibrary).catch(() => {});
    api.cacheStats().then(setCache).catch(() => {});
  }, []);

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 2000);
    return () => clearInterval(timer);
  }, [refresh]);

  useEffect(() => {
    api
      .accessConfig()
      .then((config) => {
        setAccess(config);
        setLocalUrl(config.local_url ?? "");
        setRemoteUrl(config.remote_url ?? "");
      })
      .catch(() => {});
  }, []);

  async function saveAccess() {
    const saved = await api.saveAccess(localUrl, remoteUrl);
    setAccess(saved);
    setLocalUrl(saved.local_url ?? "");
    setRemoteUrl(saved.remote_url ?? "");
    setAccessNote("Saved — the join QR now offers both addresses.");
    setTimeout(() => setAccessNote(null), 3000);
  }

  async function resync() {
    try {
      await api.triggerSync(false);
      setNote("Refreshing the library…");
    } catch {
      setNote("A sync is already running.");
    }
    refresh();
  }

  async function clearArt() {
    if (!window.confirm("Clear the cached artwork? It re-downloads as needed.")) return;
    const cleared = await api.clearCache();
    setNote(`Cleared ${formatBytes(cleared.freed_bytes)} of artwork.`);
    refresh();
  }

  async function signOut() {
    if (
      !window.confirm(
        "Sign out of Plex? You'll need to sign in again before anyone can swipe.",
      )
    )
      return;
    await api.signOut();
    navigate("/setup", { replace: true });
  }

  const lastSync = library?.last_synced_at
    ? new Date(library.last_synced_at * 1000).toLocaleString("en-GB", {
        day: "numeric",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "never";

  return (
    <div className="mx-auto min-h-dvh max-w-sm px-6 pb-16 pt-6">
      <header className="mb-8 flex items-center justify-between">
        <Link
          to="/"
          className="flex items-center gap-1 text-sm font-semibold text-spool"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
            <path
              d="M15 5l-7 7 7 7"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          Back
        </Link>
        <span className="text-xs uppercase tracking-[0.2em] text-fog">Settings</span>
      </header>

      {note && <p className="mb-4 text-sm text-spool">{note}</p>}

      <section className="mb-4 rounded-2xl bg-riser p-5">
        <h2 className="text-sm font-semibold text-stub/80">Appearance</h2>
        <div className="mt-3 flex gap-2" role="group" aria-label="Theme">
          {(["dark", "light"] as const).map((option) => (
            <button
              key={option}
              onClick={() => pickTheme(option)}
              aria-pressed={theme === option}
              className={`flex-1 rounded-xl border py-2.5 text-sm capitalize ${
                theme === option
                  ? "border-spool bg-spool/10 font-semibold text-spool"
                  : "border-hairline text-fog"
              }`}
            >
              {option === "dark" ? "🌙 Dark" : "☀️ Light"}
            </button>
          ))}
        </div>
      </section>

      <section className="mb-4 rounded-2xl bg-riser p-5">
        <h2 className="text-sm font-semibold text-stub/80">Access &amp; sharing</h2>
        <p className="mt-1 text-xs text-fog">
          The join QR uses these. Local for the sofa; remote for friends on your
          Tailscale network or reverse proxy.
        </p>
        <label className="mt-3 block text-xs text-fog" htmlFor="access-local">
          Local address
        </label>
        <input
          id="access-local"
          type="url"
          value={localUrl}
          onChange={(e) => setLocalUrl(e.target.value)}
          placeholder={access?.detected_local ?? "http://192.168.1.10:8080"}
          className="type-mono mt-1 w-full rounded-xl border border-hairline bg-house px-3 py-2.5 text-sm text-stub placeholder:text-fog/40"
        />
        {access?.detected_local && access.detected_local !== localUrl && (
          <button
            onClick={() => setLocalUrl(access.detected_local!)}
            className="mt-1 text-xs text-spool"
          >
            Use detected: {access.detected_local}
          </button>
        )}
        <label className="mt-3 block text-xs text-fog" htmlFor="access-remote">
          Remote address (Tailscale, proxy…)
        </label>
        <input
          id="access-remote"
          type="url"
          value={remoteUrl}
          onChange={(e) => setRemoteUrl(e.target.value)}
          placeholder={access?.detected_remote ?? "https://host.tailnet.ts.net"}
          className="type-mono mt-1 w-full rounded-xl border border-hairline bg-house px-3 py-2.5 text-sm text-stub placeholder:text-fog/40"
        />
        {access?.detected_remote && access.detected_remote !== remoteUrl && (
          <button
            onClick={() => setRemoteUrl(access.detected_remote!)}
            className="mt-1 text-xs text-spool"
          >
            Use detected: {access.detected_remote}
          </button>
        )}
        <button onClick={saveAccess} className="mt-3 text-sm font-semibold text-spool">
          Save addresses
        </button>
        {accessNote && <p className="mt-1.5 text-xs text-spool">{accessNote}</p>}
      </section>

      <section className="rounded-2xl bg-riser p-5">
        <h2 className="text-sm font-semibold text-stub/80">Plex connection</h2>
        {setup && (
          <dl className="mt-3 space-y-1.5 text-sm">
            <div className="flex justify-between">
              <dt className="text-fog">Server</dt>
              <dd className="text-stub/90">{setup.server_name ?? "not connected"}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-fog">Status</dt>
              <dd className={setup.stage === "ready" ? "text-stub/90" : "text-bulb"}>
                {setup.stage === "ready" ? "connected" : setup.stage}
              </dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-fog">Sections</dt>
              <dd className="type-mono text-stub/90">
                {setup.sections?.join(", ") ?? "—"}
              </dd>
            </div>
          </dl>
        )}
        <Link to="/setup" className="mt-3 inline-block text-sm font-semibold text-spool">
          Re-run setup
        </Link>
      </section>

      <section className="mt-4 rounded-2xl bg-riser p-5">
        <h2 className="text-sm font-semibold text-stub/80">Library</h2>
        {library && (
          <dl className="mt-3 space-y-1.5 text-sm">
            <div className="flex justify-between">
              <dt className="text-fog">Films</dt>
              <dd className="type-mono text-stub/90">
                {library.item_count.toLocaleString("en-GB")}
                {library.unusable_count > 0 &&
                  ` (${library.unusable_count} unusable)`}
              </dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-fog">Last synced</dt>
              <dd className="text-stub/90">{lastSync}</dd>
            </div>
            {library.state === "syncing" && (
              <div className="flex justify-between">
                <dt className="text-fog">Syncing</dt>
                <dd className="type-mono animate-pulse text-spool">
                  {library.processed}
                  {library.total ? ` / ${library.total}` : ""}
                </dd>
              </div>
            )}
          </dl>
        )}
        <button onClick={resync} className="mt-3 text-sm font-semibold text-spool">
          Refresh library
        </button>
      </section>

      <section className="mt-4 rounded-2xl bg-riser p-5">
        <h2 className="text-sm font-semibold text-stub/80">Artwork cache</h2>
        {cache && (
          <p className="mt-2 text-sm text-fog">
            <span className="type-mono text-stub/90">{cache.entries}</span> images ·{" "}
            <span className="type-mono text-stub/90">{formatBytes(cache.bytes)}</span>{" "}
            of {formatBytes(cache.cap_bytes)}
          </p>
        )}
        <button onClick={clearArt} className="mt-3 text-sm font-semibold text-spool">
          Clear cached artwork
        </button>
      </section>

      <Link
        to="/"
        className="mt-8 block w-full rounded-2xl bg-bulb py-3.5 text-center font-semibold text-press transition-transform active:scale-[0.98]"
      >
        Done
      </Link>

      <button
        onClick={signOut}
        className="mt-10 w-full rounded-2xl border border-bulb/50 py-3.5 font-semibold text-bulb"
      >
        Sign out of Plex
      </button>
    </div>
  );
}
