import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api, ApiError } from "../lib/api";
import type { SectionEntry, ServerEntry } from "../lib/types";

type Stage =
  | "loading"
  | "auth"
  | "linking"
  | "server"
  | "sections"
  | "syncing";

/** First-run wizard (§4.1): PIN sign-in in the browser (never a password),
 * paste-a-token escape hatch, server + section pickers, first sync with
 * live progress. Re-runnable from Settings. */
export function SetupWizardScreen() {
  const navigate = useNavigate();
  const [stage, setStage] = useState<Stage>("loading");
  const [error, setError] = useState<string | null>(null);

  const [pinCode, setPinCode] = useState<string | null>(null);
  const pinId = useRef<string | null>(null);
  const [servers, setServers] = useState<ServerEntry[]>([]);
  const [chosenServer, setChosenServer] = useState<string | null>(null);
  const [sections, setSections] = useState<SectionEntry[]>([]);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [showToken, setShowToken] = useState(false);
  const [token, setToken] = useState("");
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [syncLine, setSyncLine] = useState("Starting the first library sync…");

  const fail = (err: unknown, fallback: string) =>
    setError(
      err instanceof ApiError && typeof err.detail === "string"
        ? err.detail
        : fallback,
    );

  // Where are we? A wizard visit can resume any half-finished state.
  useEffect(() => {
    api
      .setupStatus()
      .then(async (status) => {
        if (status.stage === "ready") {
          const library = await api.libraryStatus();
          if (library.state === "syncing" || library.item_count === 0) {
            setStage("syncing");
          } else {
            navigate("/", { replace: true });
          }
        } else if (status.stage === "needs_sections") {
          try {
            const resp = await api.chooseServer({});
            setChosenServer(resp.machine_id);
            setSections(resp.available_sections ?? []);
            setStage("sections");
          } catch {
            setStage("auth");
          }
        } else {
          setStage("auth");
        }
      })
      .catch(() => {
        setStage("auth");
        setError("Can't reach the decide server. Is the container running?");
      });
  }, [navigate]);

  // PIN poll loop.
  useEffect(() => {
    if (stage !== "linking" || !pinId.current) return;
    const timer = setInterval(async () => {
      try {
        const poll = await api.pollPin(pinId.current!);
        if (poll.authenticated) {
          clearInterval(timer);
          setServers(poll.servers ?? []);
          setStage("server");
        } else if (poll.expired) {
          clearInterval(timer);
          setPinCode(null);
          setStage("auth");
          setError("That code expired before it was entered. Get a fresh one.");
        }
      } catch {
        /* transient — keep polling */
      }
    }, 3000);
    return () => clearInterval(timer);
  }, [stage]);

  // First-sync progress.
  useEffect(() => {
    if (stage !== "syncing") return;
    const timer = setInterval(async () => {
      try {
        const library = await api.libraryStatus();
        if (library.state === "syncing") {
          const total = library.total ? ` of ${library.total.toLocaleString("en-GB")}` : "";
          setSyncLine(
            `Syncing the library — ${library.processed.toLocaleString("en-GB")}${total} films…`,
          );
        } else if (library.item_count > 0) {
          clearInterval(timer);
          navigate("/", { replace: true });
        } else if (library.error) {
          clearInterval(timer);
          setError(`Sync failed: ${library.error}`);
        }
      } catch {
        /* transient */
      }
    }, 1000);
    return () => clearInterval(timer);
  }, [stage, navigate]);

  async function startPin() {
    setBusy(true);
    setError(null);
    try {
      const pin = await api.startPin();
      pinId.current = pin.id;
      setPinCode(pin.code);
      setStage("linking");
    } catch (err) {
      fail(err, "Couldn't reach plex.tv. Check the server has internet access.");
    } finally {
      setBusy(false);
    }
  }

  async function submitToken() {
    if (!token.trim() || !url.trim()) {
      setError("Both the token and the server address are needed.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const resp = await api.chooseServer({ token: token.trim(), url: url.trim() });
      setChosenServer(resp.machine_id);
      setSections(resp.available_sections ?? []);
      setStage("sections");
    } catch (err) {
      fail(err, "Couldn't connect with that token and address.");
    } finally {
      setBusy(false);
    }
  }

  async function pickServer(server: ServerEntry) {
    setBusy(true);
    setError(null);
    try {
      const resp = await api.chooseServer({ machine_id: server.machine_id });
      setChosenServer(resp.machine_id);
      setSections(resp.available_sections ?? []);
      setStage("sections");
    } catch (err) {
      fail(err, `Can't reach ${server.name}. Check it's on and reachable from here.`);
    } finally {
      setBusy(false);
    }
  }

  async function confirmSections() {
    if (picked.size === 0) return;
    setBusy(true);
    setError(null);
    try {
      await api.chooseServer({
        machine_id: chosenServer ?? undefined,
        sections: [...picked],
      });
      setStage("syncing");
    } catch (err) {
      fail(err, "Couldn't save the section choice.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto flex min-h-dvh max-w-sm flex-col justify-center px-6 py-12">
      <img
        src="/decide-icon-512.png"
        alt=""
        className="mx-auto mb-6 h-20 w-20 rounded-2xl"
      />
      <h1 className="type-display text-center text-xl text-stub">
        Connect decide to Plex
      </h1>

      {error && (
        <p className="mt-4 rounded-xl border border-bulb/40 bg-bulb/10 p-3 text-sm text-stub">
          {error}
        </p>
      )}

      {stage === "loading" && <p className="mt-6 text-center text-fog">One moment…</p>}

      {stage === "auth" && (
        <div className="mt-8 flex flex-col gap-3">
          <button
            onClick={startPin}
            disabled={busy}
            className="rounded-2xl bg-bulb py-4 font-semibold text-press disabled:opacity-40"
          >
            Sign in with Plex
          </button>
          <p className="text-center text-xs text-fog/70">
            You'll get a 4-character code to enter at plex.tv/link — decide never
            sees your password.
          </p>
          <button
            onClick={() => setShowToken((s) => !s)}
            className="mt-2 text-sm text-spool"
          >
            {showToken ? "Hide the token option" : "I'll paste a token instead"}
          </button>
          {showToken && (
            <div className="flex flex-col gap-3 rounded-2xl bg-riser p-4">
              <input
                type="password"
                value={token}
                onChange={(e) => setToken(e.target.value)}
                placeholder="X-Plex-Token"
                className="rounded-xl border border-hairline bg-house px-4 py-3 text-stub placeholder:text-fog/50"
              />
              <input
                type="text"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="http://192.168.1.10:32400"
                className="rounded-xl border border-hairline bg-house px-4 py-3 text-stub placeholder:text-fog/50"
              />
              <button
                onClick={submitToken}
                disabled={busy}
                className="rounded-xl bg-spool py-3 font-semibold text-press disabled:opacity-40"
              >
                Connect
              </button>
            </div>
          )}
        </div>
      )}

      {stage === "linking" && pinCode && (
        <div className="mt-8 text-center">
          <p className="text-sm text-fog">
            On any signed-in device, go to{" "}
            <a
              href="https://plex.tv/link"
              target="_blank"
              rel="noreferrer"
              className="font-semibold text-spool underline"
            >
              plex.tv/link
            </a>{" "}
            and enter:
          </p>
          <p className="type-mono mt-4 text-[44px] font-bold tracking-[0.3em] text-stub">
            {pinCode}
          </p>
          <p className="mt-4 animate-pulse text-xs text-fog/70">
            Waiting for the link…
          </p>
        </div>
      )}

      {stage === "server" && (
        <div className="mt-8">
          <h2 className="text-sm font-semibold text-stub/80">Pick your server</h2>
          <div className="mt-3 flex flex-col gap-2">
            {servers.map((server) => (
              <button
                key={server.machine_id}
                onClick={() => pickServer(server)}
                disabled={busy}
                className="rounded-xl bg-riser px-4 py-3.5 text-left text-stub disabled:opacity-40"
              >
                {server.name}
                {!server.owned && (
                  <span className="ml-2 text-xs text-fog">(shared with you)</span>
                )}
              </button>
            ))}
            {servers.length === 0 && (
              <p className="text-sm text-fog">
                No servers on this Plex account. Sign in with the account that owns
                the server, or paste a token instead.
              </p>
            )}
          </div>
        </div>
      )}

      {stage === "sections" && (
        <div className="mt-8">
          <h2 className="text-sm font-semibold text-stub/80">
            Which film libraries should decide use?
          </h2>
          <div className="mt-3 flex flex-col gap-2">
            {sections.map((section) => (
              <label
                key={section.key}
                className="flex items-center justify-between rounded-xl bg-riser px-4 py-3.5 text-stub"
              >
                <span>
                  {section.title}
                  <span className="type-mono ml-2 text-xs text-fog">
                    {section.movie_count.toLocaleString("en-GB")} films
                  </span>
                </span>
                <input
                  type="checkbox"
                  checked={picked.has(section.key)}
                  onChange={(e) => {
                    const next = new Set(picked);
                    if (e.target.checked) next.add(section.key);
                    else next.delete(section.key);
                    setPicked(next);
                  }}
                  className="h-5 w-5 accent-[#F2637A]"
                />
              </label>
            ))}
          </div>
          <button
            onClick={confirmSections}
            disabled={busy || picked.size === 0}
            className="mt-5 w-full rounded-2xl bg-bulb py-4 font-semibold text-press disabled:opacity-40"
          >
            Sync the library
          </button>
        </div>
      )}

      {stage === "syncing" && (
        <div className="mt-8 text-center">
          <p className="type-mono animate-pulse text-sm text-fog">{syncLine}</p>
          <p className="mt-3 text-xs text-fog/60">
            First sync only — after this it refreshes itself every six hours.
          </p>
        </div>
      )}
    </div>
  );
}
