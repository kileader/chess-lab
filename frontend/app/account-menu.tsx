import { authEnabled } from '../lib/auth-config';
import Link from 'next/link';

export function AccountMenu() {
  return authEnabled() ? <div className="account-menu"><Link href="/import">Import games</Link><Link href="/settings">Usernames</Link><form method="post" action="/auth/logout"><button type="submit">Sign out</button></form></div> : null;
}
