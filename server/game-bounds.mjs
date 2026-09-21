// Bounds come from the immutable queued plan, never from a caller's snapshot.
export function validGameIndex(job, index) {
  const count = job?.config?.game_count;
  return Number.isInteger(count) && Number.isInteger(index) && index >= 0 && index < count;
}
