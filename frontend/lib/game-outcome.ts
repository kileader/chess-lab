type Identity = { platform: string; username: string };
type Game = { source: string; white: string | null; black: string | null; result: string | null };

export function gameOutcome(game: Game, identities: Identity[]) {
  const usernames = new Set(identities.filter((identity) => identity.platform === game.source).map((identity) => identity.username.toLowerCase()));
  const white = usernames.has((game.white ?? '').toLowerCase());
  const black = usernames.has((game.black ?? '').toLowerCase());
  if (white === black || !['1-0', '0-1', '1/2-1/2'].includes(game.result ?? '')) return 'Unscored';
  if (game.result === '1/2-1/2') return 'Draw';
  return ((white && game.result === '1-0') || (black && game.result === '0-1')) ? 'Win' : 'Loss';
}
