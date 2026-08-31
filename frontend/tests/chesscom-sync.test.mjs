import { test } from 'node:test';
import assert from 'node:assert/strict';
import { defaultSyncDates, runChessComSync } from '../lib/chesscom-sync.ts';

const options = { username: 'Alice', date_from: '2026-01-01', date_to: '2026-08-30', time_class: 'rapid' };
const monthResult = { games_received: 3, games_added: 2, duplicates_skipped: 1, filtered_games: 4, matched_games: 3 };

test('Sync requests months sequentially, forwards filters, and totals progress', async () => {
  let inFlight = false;
  const calls = [];
  const updates = [];
  const result = await runChessComSync(options, async (path, body) => {
    assert.equal(inFlight, false);
    inFlight = true;
    await Promise.resolve();
    calls.push(body);
    inFlight = false;
    return path.endsWith('/plan') ? { months: ['2026-08', '2026-07'] } : monthResult;
  }, (progress) => updates.push(progress), () => false);
  assert.deepEqual(calls, [options, { ...options, month: '2026-08' }, { ...options, month: '2026-07' }]);
  assert.equal(result.completed, 2);
  assert.equal(result.games_added, 4);
  assert.equal(result.duplicates_skipped, 2);
  assert.equal(result.currentMonth, null);
  assert.equal(updates[0].games_added, 0);
});

test('Stop finishes the current month and makes no further month requests', async () => {
  let stop = false;
  const result = await runChessComSync(options, async (path) => {
    if (path.endsWith('/plan')) return { months: ['2026-08', '2026-07'] };
    stop = true;
    return monthResult;
  }, () => {}, () => stop);
  assert.equal(result.completed, 1);
  assert.equal(result.stopped, true);
  assert.equal(result.games_added, 2);
});

test('Partial failure retains confirmed progress and stops the run', async () => {
  let last;
  await assert.rejects(runChessComSync(options, async (path, body) => {
    if (path.endsWith('/plan')) return { months: ['2026-08', '2026-07', '2026-06'] };
    if (body.month === '2026-08') return monthResult;
    throw new Error('Rate limited');
  }, (progress) => { last = progress; }, () => false), /Rate limited/);
  assert.equal(last.completed, 1);
  assert.equal(last.games_added, 2);
  assert.equal(last.currentMonth, '2026-07');
});

test('Empty plans succeed without requesting months, and defaults cover 90 days', async () => {
  let requests = 0;
  const result = await runChessComSync(options, async () => { requests += 1; return { months: [] }; }, () => {}, () => false);
  assert.equal(requests, 1);
  assert.equal(result.games_received, 0);
  assert.deepEqual(defaultSyncDates(new Date('2026-08-30T23:59:59Z')), { date_from: '2026-06-01', date_to: '2026-08-30' });
});
