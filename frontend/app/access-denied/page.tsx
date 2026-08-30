export default function AccessDenied() {
  return <main className="connection-shell"><section className="connection-card auth-card"><div className="brand-mark">CL</div><h1>You’re on the doorstep.</h1><p>This is an invite-only beta. Ask Kevin to add the Google email you signed in with, then try again.</p><form method="post" action="/auth/logout"><button className="auth-button">Sign out</button></form></section></main>;
}
