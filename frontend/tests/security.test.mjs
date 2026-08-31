import { test } from 'node:test';
import assert from 'node:assert/strict';
import { safeReturnTo } from '../lib/auth-config.ts';
import { safeGameLink } from '../lib/safe-link.ts';
import { gameOutcome } from '../lib/game-outcome.ts';

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

test('Recent game outcomes match multiple usernames, platforms, and one side only', () => {
  const identities = [{ platform: 'lichess', username: 'Alpha' }, { platform: 'lichess', username: 'Beta' }, { platform: 'chess_com', username: 'Gamma' }];
  const game = { source: 'lichess', white: 'Opponent', black: 'BETA', result: '0-1' };
  assert.equal(gameOutcome(game, identities), 'Win');
  assert.equal(gameOutcome({ ...game, result: '1-0' }, identities), 'Loss');
  assert.equal(gameOutcome({ ...game, result: '1/2-1/2' }, identities), 'Draw');
  assert.equal(gameOutcome({ ...game, source: 'chess_com' }, identities), 'Unscored');
  assert.equal(gameOutcome({ ...game, white: 'Alpha' }, identities), 'Unscored');
  assert.equal(gameOutcome({ ...game, result: '*' }, identities), 'Unscored');
  assert.equal(gameOutcome({ ...game, source: 'chess_com', black: 'Gamma' }, identities), 'Win');
});

test('Other matches PGN player names without matching known platforms', () => {
  const identities = [{ platform: 'other', username: 'O’Connor, José' }];
  const game = { source: 'other', white: 'O’CONNOR, JOSÉ', black: 'Opponent', result: '1-0' };
  assert.equal(gameOutcome(game, identities), 'Win');
  assert.equal(gameOutcome({ ...game, source: 'lichess' }, identities), 'Unscored');
  assert.equal(gameOutcome({ ...game, source: 'chess_com' }, identities), 'Unscored');
  assert.equal(gameOutcome({ ...game, black: 'O’Connor, José' }, identities), 'Unscored');
});
