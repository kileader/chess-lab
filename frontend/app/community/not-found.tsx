import Link from 'next/link';

export default function NotFound() {
  return <section className="community-card"><h1>This share isn’t available.</h1><p>It may have been removed, or the player may have hidden their profile.</p><Link href="/community">Back to the community</Link></section>;
}
