import { cache } from 'react';
import { redirect } from 'next/navigation';
import { authEnabled } from './auth-config';
import { supabaseServer } from './supabase-server';

export type Account = { id: number; display_name: string; identities: Array<{ platform: string; username: string }> };

const bearer = cache(async () => {
  if (process.env.VERCEL && !authEnabled()) throw new Error('Hosted deployments require authentication.');
  if (!authEnabled()) return null;
  const supabase = await supabaseServer();
  // Only forward the token. The API verifies it with Supabase before using any identity.
  const { data } = await supabase.auth.getSession();
  if (!data.session) redirect('/login');
  return data.session.access_token;
});

async function requestApi(path: string, init?: RequestInit) {
  const token = await bearer();
  const headers = new Headers(init?.headers);
  if (token) headers.set('Authorization', `Bearer ${token}`);
  const base = process.env.CHESSLAB_API_URL ?? 'http://127.0.0.1:8000';
  if (!path.startsWith('/api/')) throw new Error('Invalid API path');
  return fetch(`${base}${path}`, { ...init, headers, cache: 'no-store' });
}

export const currentAccount = cache(async (): Promise<Account> => {
  const response = await requestApi('/api/account');
  if (response.status === 401) redirect('/login?reason=expired');
  if (response.status === 403) redirect('/access-denied');
  if (!response.ok) throw new Error('Your account is unavailable. Please try again shortly.');
  return response.json() as Promise<Account>;
});

export async function requireAccount() {
  const account = await currentAccount();
  if (authEnabled() && !account.identities.length) redirect('/onboarding');
  return account;
}

export async function serverApi(path: string, init?: RequestInit) {
  if (path.startsWith('/api/me/')) {
    const account = await currentAccount();
    path = path.replace('/api/me/', `/api/users/${account.id}/`);
  }
  return requestApi(path, init);
}
