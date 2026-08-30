export type PracticePosition = {
  id: number; family: string; fen: string; player_color: 'white' | 'black';
  line: string[]; san_path: string[]; note: string; candidate_move: string;
  date_from: string | null; date_to: string | null; created_at: string;
  examples: Array<{ date: string | null; result: string | null; source_url: string | null }>;
};

export function practicePositionHref(position: PracticePosition) {
  const query = new URLSearchParams({ color: position.player_color, line: position.line.join(',') });
  if (position.date_from) query.set('date_from', position.date_from);
  else query.set('period', 'all');
  if (position.date_to) query.set('date_to', position.date_to);
  return `/openings/${encodeURIComponent(position.family)}?${query}#explorer`;
}

export async function practiceError(response: Response, fallback: string) {
  const body = await response.json().catch(() => null) as { detail?: unknown } | null;
  return typeof body?.detail === 'string' ? body.detail : fallback;
}
