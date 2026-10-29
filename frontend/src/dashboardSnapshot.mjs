/** Keep the last successful snapshot when an individual read fails or is absent. */
export function snapshotRows(previous, incoming, failed = false) {
  if (failed || !Array.isArray(incoming)) return previous;
  // Identical live refreshes should not rebuild tables and replay their effects.
  return JSON.stringify(previous) === JSON.stringify(incoming) ? previous : incoming;
}
