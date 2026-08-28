type RepertoireItem = {
  id: number;
  context: string;
  opening: string;
  status: 'keep' | 'practice' | 'try';
  note: string;
};

const apiBase = process.env.CHESSLAB_API_URL ?? 'http://127.0.0.1:8000';

const statusCopy = {
  keep: 'Keep',
  practice: 'Practice',
  try: 'Try it',
} as const;

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
  const contexts = ['As White', 'As Black vs 1.e4', 'As Black vs 1.d4'];

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
          <p>This is your short list—not a verdict from the stats. Keep what feels like yours, practice what needs work, and test the choices you have not decided on yet.</p>
        </section>

        {items === null ? (
          <section className="panel repertoire-empty"><h2>Your plan is unavailable right now.</h2><p>Start the local Chess Lab API, then refresh this page.</p></section>
        ) : items.length === 0 ? (
          <section className="panel repertoire-empty"><h2>Your plan is empty.</h2><p>Add the openings you want to keep, practice, or try.</p></section>
        ) : (
          <section className="repertoire-grid" aria-label="Opening repertoire">
            {contexts.map((context) => {
              const contextItems = items.filter((item) => item.context === context);
              return (
                <article className="panel repertoire-lane" key={context}>
                  <div className="panel-heading">
                    <div><p className="eyebrow">{context === 'As White' ? 'First move' : 'Defensive plan'}</p><h2>{context}</h2></div>
                  </div>
                  {contextItems.length ? <div className="repertoire-list">
                    {contextItems.map((item) => (
                      <a className="repertoire-item" href={`/openings/${encodeURIComponent(item.opening)}`} key={item.id}>
                        <span className={`repertoire-status status-${item.status}`}>{statusCopy[item.status]}</span>
                        <div><strong>{item.opening}</strong><p>{item.note}</p></div>
                        <span aria-hidden="true">→</span>
                      </a>
                    ))}
                  </div> : <p className="repertoire-empty-copy">Nothing decided here yet.</p>}
                </article>
              );
            })}
          </section>
        )}
      </div>
    </main>
  );
}
