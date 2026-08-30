import { authEnabled } from '../lib/auth-config';

export function AccountMenu() {
  return authEnabled() ? <form method="post" action="/auth/logout" className="account-menu"><button type="submit">Sign out</button></form> : null;
}
