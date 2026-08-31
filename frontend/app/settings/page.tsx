import Link from 'next/link';
import { currentAccount } from '../../lib/api-server';
import { authEnabled } from '../../lib/auth-config';
import { AccountMenu } from '../account-menu';
import { IdentityForm } from './identity-form';

export const dynamic = 'force-dynamic';

export default async function Settings() {
  const account = await currentAccount();
  return <main className="connection-shell"><section className="connection-card auth-card identity-card">
    <Link href="/" className="settings-back">← Back to your dashboard</Link>
    <p className="eyebrow">Account settings</p><h1>Your chess usernames.</h1>
    <p>Add the accounts you play on, or correct a typo. We combine their results and use each username to identify your side in imported games.</p>
    {authEnabled() ? <IdentityForm initialIdentities={account.identities} /> : <p>Username settings are available when signed in with Google. Your legacy local profile is unchanged.</p>}
    {authEnabled() && <p><Link className="sync-import-link" href="/community/sharing">Manage your public profile and shared games →</Link><br />Nothing is shared until you choose to publish it.</p>}
    {authEnabled() && account.identities.filter((identity) => identity.platform === 'chess_com' || identity.platform === 'lichess').map((identity) => <p key={`${identity.platform}:${identity.username}`}><Link className="sync-import-link" href={`/import?platform=${identity.platform}&username=${encodeURIComponent(identity.username)}`}>Sync {identity.platform === 'lichess' ? 'Lichess' : 'Chess.com'} games for {identity.username} →</Link></p>)}
    <AccountMenu />
  </section></main>;
}
