export function safeGameLink(value: string | null) {
  if (!value) return '#';
  try {
    const url = new URL(value);
    return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password ? url.href : '#';
  } catch { return '#'; }
}
