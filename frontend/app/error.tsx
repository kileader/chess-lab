'use client';

import Link from 'next/link';

export default function AppError({ reset }: { reset: () => void }) {
  return <main className="connection-shell"><section className="connection-card auth-card"><div className="brand-mark">CL</div><h1>We couldn’t load your workspace.</h1><p>The service may be restarting or sign-in may need attention. Your saved data has not been changed.</p><button className="auth-button" onClick={reset}>Try again</button><p><Link href="/login">Return to sign-in</Link></p></section></main>;
}
