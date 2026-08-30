import { NextResponse } from 'next/server';
import { authEnabled } from '../../../lib/auth-config';
import { supabaseServer } from '../../../lib/supabase-server';

export async function GET() {
  if (!authEnabled()) return new NextResponse('Google sign-in is not configured.', { status: 503 });
  const origin = process.env.NEXT_PUBLIC_SITE_URL;
  if (!origin) return new NextResponse('Site URL is not configured.', { status: 503 });
  const supabase = await supabaseServer();
  const { data, error } = await supabase.auth.signInWithOAuth({
    provider: 'google', options: { redirectTo: `${new URL(origin).origin}/auth/callback`, skipBrowserRedirect: true },
  });
  if (error || !data.url) return NextResponse.redirect(new URL('/login?reason=failed', origin));
  return NextResponse.redirect(data.url);
}
