import Link from 'next/link';
import { authEnabled } from '../../lib/auth-config';

export const dynamic = 'force-dynamic';

export default async function Login({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const params = await searchParams;
  return <main className="connection-shell"><section className="connection-card auth-card">
    <div className="brand-mark">CL</div><p className="eyebrow">Chess Lab · Beta</p>
    <h1>Your games.<br />Your discoveries.</h1>
    <p>Sign in to explore your archive and keep a personal opening plan. Your imports and study notes are private.</p>
    {params.reason && <p role="alert">{params.reason === 'expired' ? 'Your session expired. Please sign in again.' : 'Sign-in did not complete. Please try again.'}</p>}
    {authEnabled() ? <a className="auth-button" href="/auth/login">Continue with Google</a> : <><p>Google sign-in is not enabled in this local preview.</p><Link href="/">Return to your local dashboard →</Link></>}
    <small>No chess-platform password is needed. Your library stays private.</small>
  </section></main>;
}
