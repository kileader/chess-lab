import { RepertoireBoard, type RepertoireItem } from './repertoire-board';
import { PracticePositions } from './practice-positions';
import type { PracticePosition } from '../practice-position';
import { requireAccount, serverApi } from '../../lib/api-server';
import { AccountMenu } from '../account-menu';

export const dynamic = 'force-dynamic';

async function loadRepertoire(): Promise<RepertoireItem[] | null> {
  try {
    const response = await serverApi('/api/me/repertoire', {
      cache: 'no-store',
    });
    if (!response.ok) return null;
    return response.json() as Promise<RepertoireItem[]>;
  } catch {
    return null;
  }
}

export default async function RepertoirePage() {
  const account = await requireAccount();
  const [items, positions] = await Promise.all([
    loadRepertoire(),
    serverApi('/api/me/practice-positions', { cache: 'no-store' })
      .then((response) => response.ok ? response.json() as Promise<PracticePosition[]> : null)
      .catch(() => null),
  ]);

  return (
    <main className="app-shell">
      <header className="topbar">
        <a className="brand" href="/#top" aria-label="Chess Lab home">
          <span className="brand-mark">CL</span>
          <span>Chess Lab</span>
        </a>
        <nav aria-label="Primary navigation">
          <a href="/#overview">Overview</a>
          <a href="/#openings">Openings</a>
          <a className="nav-active" href="/repertoire">Repertoire</a>
          <a href="/#games">Games</a>
          <a href="/#upload">Import</a>
        </nav>
        <div className="profile-pill"><span className="status-dot" /><span>{account.display_name}</span><AccountMenu /></div>
      </header>

      <div className="detail-shell repertoire-shell">
        <a className="back-link" href="/#openings">← Back to your opening data</a>
        <section className="repertoire-hero">
          <p className="eyebrow">Your opening plan</p>
          <h1>What you want<br />to play.</h1>
          <p>Keep a short list of ideas you actually want to test. Chess Lab brings your real game record into the picture, but the choices stay yours.</p>
        </section>

        {positions === null ? <section className="panel repertoire-empty"><h2>Practice positions are unavailable right now.</h2><p>Please refresh in a moment.</p></section> : <PracticePositions initialItems={positions} userId={account.id} />}

        {items === null ? (
          <section className="panel repertoire-empty"><h2>Your plan is unavailable right now.</h2><p>Please refresh in a moment.</p></section>
        ) : <RepertoireBoard initialItems={items} userId={account.id} />}
      </div>
    </main>
  );
}
