'use client';

export default function CommunityError({ reset }: { reset: () => void }) {
  return <section className="community-card"><h1>We couldn’t load the community.</h1><p>Your private library has not been changed.</p><button className="auth-button" onClick={reset}>Try again</button></section>;
}
