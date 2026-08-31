import Link from 'next/link';
import { communityPage, type CommunityProfile, type SharedGame } from '../../lib/community';
import { publicCommunity } from '../../lib/community-server';
import { GameCard, PageLinks } from './game-card';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'Community · Chess Lab', description: 'Games and study ideas shared by Chess Lab players.' };

export default async function Community({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = await searchParams;
  const page = communityPage(params.page), people = communityPage(params.people);
  const data = await publicCommunity<{ games: SharedGame[]; profiles: CommunityProfile[] }>(`/api/community?offset=${page * 20}&people_offset=${people * 20}`);
  return <>
    <section className="community-intro"><p className="eyebrow">A shared study room</p><h1>What are you playing?</h1>
      <p>Browse games players chose to share. Replay a line, meet another player, or bring a game of your own.</p>
      <Link className="auth-button community-action" href="/community/sharing">Choose what to share</Link></section>
    <div className="community-columns"><section aria-labelledby="shared-games"><h2 id="shared-games">Recently shared</h2>
      <div className="community-stack">{data.games.map(game => <GameCard key={game.public_id} game={game} />)}</div>
      {!data.games.length && <div className="community-card"><h3>{page ? 'No more games here.' : 'The first move is yours.'}</h3><p>No games have been shared on this page. Your private imports never appear automatically.</p></div>}
      <PageLinks page={page} hasNext={data.games.length === 20} href={next => `/community?page=${next}&people=${people}`} />
    </section><aside aria-labelledby="community-players"><h2 id="community-players">Players</h2>
      <div className="community-stack">{data.profiles.map(profile => <article className="community-card" key={profile.public_id}>
        <h3><Link href={`/community/players/${profile.public_id}`}>{profile.name}</Link></h3>
        {profile.bio && <p className="community-caption">{profile.bio}</p>}<small>{profile.shared_games} shared games</small>
      </article>)}</div>
      {!data.profiles.length && <p>No public profiles on this page yet.</p>}
      <PageLinks page={people} hasNext={data.profiles.length === 20} href={next => `/community?page=${page}&people=${next}`} />
    </aside></div>
  </>;
}
