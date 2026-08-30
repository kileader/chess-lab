import { NextResponse, type NextRequest } from 'next/server';
import { safeReturnTo } from '../../../lib/auth-config';
import { supabaseServer } from '../../../lib/supabase-server';

export async function GET(request: NextRequest) {
  const origin = process.env.NEXT_PUBLIC_SITE_URL;
  if (!origin) return new NextResponse('Site URL is not configured.', { status: 503 });
  const code = request.nextUrl.searchParams.get('code');
  if (code) {
    const supabase = await supabaseServer();
    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (!error) return NextResponse.redirect(new URL(safeReturnTo(request.nextUrl.searchParams.get('next')), origin));
  }
  return NextResponse.redirect(new URL('/login?reason=failed', origin));
}
