/** Per-session identity kept client-side (the auth itself is the httpOnly
 * cookie — this is only so the UI knows which participant is "you"). */

export function savePid(sessionId: string, participantId: string): void {
  localStorage.setItem(`decide-pid-${sessionId}`, participantId);
}

export function getPid(sessionId: string): string | null {
  return localStorage.getItem(`decide-pid-${sessionId}`);
}

export function saveName(name: string): void {
  localStorage.setItem("decide-name", name);
}

export function getName(): string {
  return localStorage.getItem("decide-name") ?? "";
}

export interface SessionRecord {
  id: string;
  code: string;
  deck_size: number;
  saved_at: number;
}

const RECORDS_KEY = "decide-sessions";
const MAX_RECORDS = 8;

export function recordSession(record: Omit<SessionRecord, "saved_at">): void {
  const list = listSessions().filter((r) => r.id !== record.id);
  list.unshift({ ...record, saved_at: Date.now() });
  localStorage.setItem(RECORDS_KEY, JSON.stringify(list.slice(0, MAX_RECORDS)));
}

export function listSessions(): SessionRecord[] {
  try {
    return JSON.parse(localStorage.getItem(RECORDS_KEY) ?? "[]") as SessionRecord[];
  } catch {
    return [];
  }
}

export function dropSession(sessionId: string): void {
  localStorage.setItem(
    RECORDS_KEY,
    JSON.stringify(listSessions().filter((r) => r.id !== sessionId)),
  );
}
