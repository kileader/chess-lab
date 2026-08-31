import Link from 'next/link';

export default function CommunityLayout({ children }: { children: React.ReactNode }) {
  return <main className="community-shell">
    <header className="community-header"><Link className="brand" href="/community"><span className="brand-mark">CL</span>Chess Lab community</Link>
      <nav aria-label="Community"><Link href="/">My workspace</Link><Link href="/community/sharing">Manage sharing</Link></nav></header>
    {children}
    <footer className="community-footer">Shared by players, not verified chess accounts. Only deliberately published games appear here.</footer>
  </main>;
}
