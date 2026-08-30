import { NextResponse, type NextRequest } from 'next/server';
import { supabaseServer } from '../../../lib/supabase-server';

export async function POST(request: NextRequest) {
  const origin = process.env.NEXT_PUBLIC_SITE_URL;
  if (!origin || request.headers.get('origin') !== new URL(origin).origin) return new NextResponse('Forbidden', { status: 403 });
  const supabase = await supabaseServer();
  const { error } = await supabase.auth.signOut();
  if (error) return new NextResponse('Sign-out failed. Please try again.', { status: 503 });
  return NextResponse.redirect(new URL('/login', origin), 303);
}
