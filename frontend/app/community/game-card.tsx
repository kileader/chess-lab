import Link from 'next/link';
import { gameTitle, type SharedGame } from '../../lib/community';

export function GameCard({ game }: { game: SharedGame }) {
  return <article className="community-card">
    <p className="eyebrow">Shared by <Link href={`/community/players/${game.profile_id}`}>{game.name}</Link></p>
    <h2><Link href={`/community/games/${game.public_id}`}>{gameTitle(game)}</Link></h2>
    <p className="community-meta">{game.opening ?? 'Unclassified opening'} · {game.result ?? 'Unknown result'}</p>
    <p className="community-meta">{game.date ?? 'Undated'} · {game.source ?? 'PGN'} · {game.time_control ?? 'Unknown time control'}</p>
    {game.caption && <p className="community-caption">{game.caption}</p>}
    <Link className="sync-import-link" href={`/community/games/${game.public_id}`}>Replay game →</Link>
  </article>;
}

export function PageLinks({ page, hasNext, href }: { page: number; hasNext: boolean; href: (page: number) => string }) {
  return <nav className="community-pagination" aria-label="Pagination">
    {page > 0 && <Link href={href(page - 1)}>← Previous</Link>}
    <span>Page {page + 1}</span>
    {hasNext && <Link href={href(page + 1)}>Next →</Link>}
  </nav>;
}
