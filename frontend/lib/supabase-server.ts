import { createServerClient } from '@supabase/ssr';
import { cookies } from 'next/headers';
import { authConfig } from './auth-config';

export async function supabaseServer() {
  const cookieStore = await cookies();
  const { url, key } = authConfig();
  return createServerClient(url, key, {
    cookies: {
      getAll: () => cookieStore.getAll(),
      setAll: (values) => {
        try { values.forEach(({ name, value, options }) => cookieStore.set(name, value, options)); }
        catch { /* Server Components cannot write cookies; middleware refreshes them. */ }
      },
    },
  });
}
