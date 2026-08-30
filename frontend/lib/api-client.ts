'use client';

import { createBrowserClient } from '@supabase/ssr';
import { authConfig, authEnabled } from './auth-config';

export async function apiFetch(path: string, init?: RequestInit) {
  const headers = new Headers(init?.headers);
  if (authEnabled()) {
    const { url, key } = authConfig();
    const supabase = createBrowserClient(url, key);
    const { data, error } = await supabase.auth.getSession();
    if (error || !data.session) throw new Error('Your session has expired. Sign in again to continue.');
    headers.set('Authorization', `Bearer ${data.session.access_token}`);
  }
  if (!path.startsWith('/api/')) throw new Error('Invalid API path');
  const base = process.env.NEXT_PUBLIC_CHESSLAB_API_URL ?? 'http://127.0.0.1:8000';
  return fetch(`${base}${path}`, { ...init, headers, cache: 'no-store' });
}
