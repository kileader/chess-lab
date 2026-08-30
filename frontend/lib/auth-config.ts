export function authEnabled() {
  return process.env.NEXT_PUBLIC_CHESSLAB_AUTH_MODE === 'supabase';
}

export function authConfig() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
  if (!url || !key) throw new Error('Google sign-in is not configured yet.');
  return { url, key };
}

export function safeReturnTo(value: string | null) {
  if (!value?.startsWith('/') || value.startsWith('//') || value.includes('\\')
      || [...value].some((character) => character.charCodeAt(0) < 32 || character.charCodeAt(0) === 127)) return '/';
  try { return new URL(value, 'https://chesslab.invalid').origin === 'https://chesslab.invalid' ? value : '/'; }
  catch { return '/'; }
}
