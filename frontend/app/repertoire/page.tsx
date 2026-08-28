import { RepertoireBoard, type RepertoireItem } from './repertoire-board';

const apiBase = process.env.CHESSLAB_API_URL ?? 'http://127.0.0.1:8000';

async function loadRepertoire(): Promise<RepertoireItem[] | null> {
  try {
    const response = await fetch(`${apiBase}/api/users/1/repertoire`, {
      cache: 'no-store',
    });
    if (!response.ok) return null;
    return response.json() as Promise<RepertoireItem[]>;
  } catch {
    return null;
  }
}

export default async function RepertoirePage() {
  const items = await loadRepertoire();

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
        <div className="profile-pill"><span className="status-dot" /><span>Local plan</span></div>
      </header>

      <div className="detail-shell repertoire-shell">
        <a className="back-link" href="/#openings">← Back to your opening data</a>
        <section className="repertoire-hero">
          <p className="eyebrow">Your opening plan</p>
          <h1>What you want<br />to play.</h1>
          <p>Keep a short list of ideas you actually want to test. Chess Lab brings your real game record into the picture, but the choices stay yours.</p>
        </section>

        {items === null ? (
          <section className="panel repertoire-empty"><h2>Your plan is unavailable right now.</h2><p>Start the local Chess Lab API, then refresh this page.</p></section>
        ) : <RepertoireBoard initialItems={items} />}
      </div>
    </main>
  );
}
