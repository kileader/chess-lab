import { redirect } from 'next/navigation';
import { currentAccount } from '../../lib/api-server';
import { AccountMenu } from '../account-menu';
import { SetupForm } from './setup-form';

export const dynamic = 'force-dynamic';

export default async function Onboarding() {
  const account = await currentAccount();
  if (account.identities.length) redirect('/');
  return <main className="connection-shell"><section className="connection-card auth-card"><div className="brand-mark">CL</div><h1>Which player<br />are you?</h1><p>Your chess username tells us which side you played in your imports. It doesn’t connect to your chess account or access anyone else’s library.</p><SetupForm /><AccountMenu /></section></main>;
}
