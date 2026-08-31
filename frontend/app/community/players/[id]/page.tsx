import { cache } from 'react';
import { notFound } from 'next/navigation';
import Link from 'next/link';
import { communityPage, publicRecordId, recordMetadata, type CommunityProfile, type SharedGame } from '../../../../lib/community';
import { publicCommunity } from '../../../../lib/community-server';
import { GameCard, PageLinks } from '../../game-card';

export const dynamic = 'force-dynamic';
const profileData = cache(async (id: string, page: number) => {
  if (!publicRecordId(id)) notFound();
  return publicCommunity<{ profile: CommunityProfile; games: SharedGame[] }>(`/api/community/profiles/${id}?offset=${page * 20}`);
});
type Props = { params: Promise<{ id: string }>; searchParams: Promise<Record<string, string | string[] | undefined>> };

export async function generateMetadata({ params, searchParams }: Props) {
  const data = await profileData((await params).id, communityPage((await searchParams).page));
  return recordMetadata(data.profile.name, data.profile.bio || 'Games this player chose to share on Chess Lab.');
}

export default async function Player({ params, searchParams }: Props) {
  const { id } = await params;
  const page = communityPage((await searchParams).page);
  const { profile, games } = await profileData(id, page);
  return <><Link href="/community">← Community</Link><section className="community-intro"><p className="eyebrow">Public player profile</p>
    <h1>{profile.name}</h1><p className="community-caption">{profile.bio || 'Here to study chess together.'}</p>
    <p>{profile.shared_games} deliberately shared games. This is not their full library.</p></section>
    <div className="community-stack">{games.map(game => <GameCard key={game.public_id} game={game} />)}</div>
    {!games.length && <p>No shared games on this page yet.</p>}
    <PageLinks page={page} hasNext={games.length === 20} href={next => `/community/players/${id}?page=${next}`} /></>;
}
