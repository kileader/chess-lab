import { test } from 'node:test';
import assert from 'node:assert/strict';
import { safeReturnTo } from '../lib/auth-config.ts';
import { safeGameLink } from '../lib/safe-link.ts';

test('OAuth return paths cannot escape the site', () => {
  for (const value of [null, '//evil.example', '/\\evil.example', 'https://evil.example', '/\t/evil.example', '/\n/evil.example', 'javascript:alert(1)']) {
    assert.equal(safeReturnTo(value), '/');
  }
  assert.equal(safeReturnTo('/repertoire?tab=practice#position'), '/repertoire?tab=practice#position');
});

test('Imported PGN links cannot use executable schemes or embedded credentials', () => {
  for (const value of [null, 'javascript:alert(1)', 'data:text/html,hello', 'file:///etc/passwd', 'https://user:secret@example.com']) assert.equal(safeGameLink(value), '#');
  assert.equal(safeGameLink('https://lichess.org/12345678'), 'https://lichess.org/12345678');
});
