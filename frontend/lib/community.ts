export type CommunityProfile = { public_id: string; name: string; bio: string; shared_games: number };
export type SharedGame = {
  public_id: string; profile_id: string; name: string; caption: string; shared_at: string;
  white: string | null; black: string | null; white_elo: number | null; black_elo: number | null;
  result: string | null; opening: string | null; date: string | null; time_control: string | null;
  source: string | null;
};
export type SharedGameDetail = SharedGame & { positions: string[]; moves: string[] };
export type SharingSettings = { public_id: string | null; name: string; bio: string; visible: boolean };
export type ShareableGame = { id: number; white: string | null; black: string | null; date: string | null;
  result: string | null; opening: string | null; share_id: string | null; caption: string | null };

export function communityPage(value: string | string[] | undefined) {
  const page = Number(value);
  return Number.isSafeInteger(page) && page >= 0 && page <= 50000 ? page : 0;
}

export function publicRecordId(value: string) {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
}

export function gameTitle(game: SharedGame) {
  return `${game.white ?? 'Unknown'} vs ${game.black ?? 'Unknown'}`;
}

export function recordMetadata(title: string, description: string) {
  return { title: `${title} · Chess Lab`, description,
    openGraph: { title, description, images: [] },
    twitter: { card: 'summary' as const, title, description, images: [] },
    robots: { index: false, follow: false } };
}
