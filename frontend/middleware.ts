import { createServerClient } from '@supabase/ssr';
import { NextResponse, type NextRequest } from 'next/server';
import { authConfig, authEnabled } from './lib/auth-config';

export async function middleware(request: NextRequest) {
  if (process.env.VERCEL && !authEnabled()) return new NextResponse('Sign-in must be configured before this deployment can be used.', { status: 503 });
  let response = NextResponse.next({ request });
  const publicCommunityPage = request.nextUrl.pathname === '/community' ||
    request.nextUrl.pathname.startsWith('/community/players/') || request.nextUrl.pathname.startsWith('/community/games/');
  if (authEnabled() && !publicCommunityPage) {
    const { url, key } = authConfig();
    const supabase = createServerClient(url, key, { cookies: {
      getAll: () => request.cookies.getAll(),
      setAll: (values) => {
        values.forEach(({ name, value }) => request.cookies.set(name, value));
        response = NextResponse.next({ request });
        values.forEach(({ name, value, options }) => response.cookies.set(name, value, options));
      },
    } });
    await supabase.auth.getClaims();
  }
  response.headers.set('Cache-Control', 'private, no-store');
  response.headers.set('Referrer-Policy', 'strict-origin-when-cross-origin');
  response.headers.set('X-Content-Type-Options', 'nosniff');
  response.headers.set('X-Frame-Options', 'DENY');
  return response;
}

export const config = { matcher: ['/((?!_next/static|_next/image|favicon.ico|og.png).*)'] };
