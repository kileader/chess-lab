import { cache } from 'react';
import { notFound } from 'next/navigation';
import { publicRecordId, type SharedGameDetail } from './community';

// Public requests deliberately contain no session, bearer token, or private API path.
export async function publicCommunity<T>(path: string): Promise<T> {
  if (path !== '/api/community' && !path.startsWith('/api/community?') &&
      !path.startsWith('/api/community/profiles/') && !path.startsWith('/api/community/games/')) {
    throw new Error('Invalid community path');
  }
  const base = process.env.CHESSLAB_API_URL ?? 'http://127.0.0.1:8000';
  const response = await fetch(`${base}${path}`, { cache: 'no-store' });
  if (response.status === 404) notFound();
  if (!response.ok) throw new Error('The community is temporarily unavailable. Please try again.');
  return response.json() as Promise<T>;
}

export const sharedGame = cache(async (id: string) => {
  if (!publicRecordId(id)) notFound();
  return publicCommunity<SharedGameDetail>(`/api/community/games/${id}`);
});
