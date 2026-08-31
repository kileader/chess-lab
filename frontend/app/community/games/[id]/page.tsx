import Link from 'next/link';
import { gameTitle, recordMetadata } from '../../../../lib/community';
import { sharedGame } from '../../../../lib/community-server';
import { Replay } from './replay';

export const dynamic = 'force-dynamic';
type Props = { params: Promise<{ id: string }> };

export async function generateMetadata({ params }: Props) {
  const game = await sharedGame((await params).id);
  return recordMetadata(gameTitle(game), `${game.opening ?? 'Chess game'} · Shared by ${game.name}. ${game.caption}`);
}

export default async function Game({ params }: Props) {
  const game = await sharedGame((await params).id);
  return <><Link href="/community">← Community</Link><section className="community-intro">
    <p className="eyebrow">Shared by <Link href={`/community/players/${game.profile_id}`}>{game.name}</Link></p>
    <h1>{gameTitle(game)}</h1><p>{game.opening ?? 'Unclassified opening'} · {game.result ?? 'Unknown result'} · {game.date ?? 'Undated'}</p>
    <p>White: {game.white_elo ?? 'Unrated'} · Black: {game.black_elo ?? 'Unrated'} · {game.time_control ?? 'Unknown time control'}</p>
    {game.caption && <p className="community-caption">{game.caption}</p>}
  </section><Replay positions={game.positions} moves={game.moves} />
  <p className="community-meta">Only the main line is shared. Original PGN comments, variations, and private study notes are not included. Copy this page’s URL to share it.</p></>;
}
