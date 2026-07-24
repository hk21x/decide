/** "Open in Plex": try the app scheme, fall back to the web player.
 * Scheme shape verified in docs/plex-notes.md §8. */

export function plexAppUrl(itemId: string, machineId: string): string {
  const key = encodeURIComponent(`/library/metadata/${itemId}`);
  return `plex://preplay/?metadataKey=${key}&metadataType=1&server=${machineId}`;
}

export function plexWebUrl(itemId: string, machineId: string): string {
  const key = encodeURIComponent(`/library/metadata/${itemId}`);
  return `https://app.plex.tv/desktop/#!/server/${machineId}/details?key=${key}`;
}

export function openInPlex(itemId: string, machineId: string): void {
  const started = Date.now();
  window.location.href = plexAppUrl(itemId, machineId);
  // If the app took over, the page hides and the timer never matters.
  window.setTimeout(() => {
    if (!document.hidden && Date.now() - started < 2500) {
      window.open(plexWebUrl(itemId, machineId), "_blank", "noopener");
    }
  }, 1400);
}
