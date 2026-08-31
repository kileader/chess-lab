export type SyncOptions = {
  username: string;
  date_from: string;
  date_to: string;
  time_class: string;
};

export type SyncProgress = {
  total: number;
  completed: number;
  currentMonth: string | null;
  games_received: number;
  games_added: number;
  duplicates_skipped: number;
  filtered_games: number;
  matched_games: number;
  stopped: boolean;
};

export const emptySyncProgress = (): SyncProgress => ({
  total: 0, completed: 0, currentMonth: null, games_received: 0, games_added: 0,
  duplicates_skipped: 0, filtered_games: 0, matched_games: 0, stopped: false,
});

export function defaultSyncDates(today: Date) {
  const from = new Date(today);
  from.setUTCDate(from.getUTCDate() - 90);
  return { date_from: from.toISOString().slice(0, 10), date_to: today.toISOString().slice(0, 10) };
}

// Keep requests sequential. Each completed month is durable; restarting deduplicates.
export async function runChessComSync(
  options: SyncOptions,
  request: (path: string, body: Record<string, string>) => Promise<unknown>,
  onProgress: (progress: SyncProgress) => void,
  shouldStop: () => boolean,
): Promise<SyncProgress> {
  const progress = emptySyncProgress();
  const plan = await request('/api/games/sync/chess-com/plan', options) as { months: string[] };
  progress.total = plan.months.length;
  onProgress({ ...progress });
  for (const month of plan.months) {
    if (shouldStop()) { progress.stopped = true; break; }
    progress.currentMonth = month;
    onProgress({ ...progress });
    const result = await request('/api/games/sync/chess-com/month', { ...options, month }) as Pick<SyncProgress,
      'games_received' | 'games_added' | 'duplicates_skipped' | 'filtered_games' | 'matched_games'>;
    for (const key of ['games_received', 'games_added', 'duplicates_skipped', 'filtered_games', 'matched_games'] as const) {
      progress[key] += result[key];
    }
    progress.completed += 1;
    progress.currentMonth = null;
    onProgress({ ...progress });
  }
  progress.currentMonth = null;
  onProgress({ ...progress });
  return progress;
}
