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
