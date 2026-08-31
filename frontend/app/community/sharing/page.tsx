import { requireAccount, serverApi } from '../../../lib/api-server';
import { authEnabled } from '../../../lib/auth-config';
import { communityPage, type SharingSettings, type ShareableGame } from '../../../lib/community';
import { PageLinks } from '../game-card';
import { SharingControls } from './sharing-controls';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'Manage sharing · Chess Lab', robots: { index: false, follow: false } };

export default async function Sharing({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  await requireAccount();
  if (!authEnabled()) return <section className="community-card"><h1>Sharing requires Google sign-in.</h1><p>Your legacy local library stays private and cannot be published from local-auth mode.</p></section>;
  const page = communityPage((await searchParams).page);
  const [settingsResponse, gamesResponse] = await Promise.all([
    serverApi('/api/account/sharing'), serverApi(`/api/account/sharing/games?offset=${page * 20}`),
  ]);
  if (!settingsResponse.ok || !gamesResponse.ok) throw new Error('Could not load sharing settings.');
  const settings = await settingsResponse.json() as SharingSettings;
  const library = await gamesResponse.json() as { total: number; games: ShareableGame[] };
  return <><section className="community-intro"><p className="eyebrow">You choose what leaves your workspace</p><h1>Share a game. Keep the rest.</h1>
    <p>Nothing is public by default. Set up a public profile, then choose individual games to share with the community or on Discord.</p></section>
    <SharingControls key={`${JSON.stringify(settings)}:${page}:${JSON.stringify(library.games)}`} initial={settings} games={library.games} />
    {!library.total && <p>Your library is empty. Import games before choosing one to share.</p>}
    <PageLinks page={page} hasNext={(page + 1) * 20 < library.total} href={next => `/community/sharing?page=${next}`} />
  </>;
}
