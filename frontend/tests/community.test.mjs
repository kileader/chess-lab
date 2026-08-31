import { test } from 'node:test';
import assert from 'node:assert/strict';
import { communityPage, publicRecordId, recordMetadata, gameTitle } from '../lib/community.ts';

test('Public page parameters cannot become traversal or unbounded offsets', () => {
  for (const input of [undefined, '-1', '1.2', 'Infinity', '50001', '../account', ['2', '3']]) {
    assert.equal(communityPage(input), 0);
  }
  assert.equal(communityPage('2'), 2);
  assert.equal(publicRecordId('12345678-1234-1234-1234-123456789012'), true);
  for (const input of ['../account', 'alice', '123?private=1', '']) assert.equal(publicRecordId(input), false);
});

test('Shared game and profile metadata are record-specific and clear inherited images', () => {
  const title = gameTitle({ white: 'Alice', black: 'Bob' });
  assert.equal(title, 'Alice vs Bob');
  assert.equal(gameTitle({ white: null, black: null }), 'Unknown vs Unknown');
  for (const [name, description] of [[title, 'Philidor Defense'], ['Public Alice', 'Learning chess']]) {
    const meta = recordMetadata(name, description);
    assert.equal(meta.title, `${name} · Chess Lab`);
    assert.equal(meta.description, description);
    assert.equal(meta.openGraph.title, name);
    assert.equal(meta.twitter.description, description);
    assert.deepEqual(meta.openGraph.images, []);
    assert.deepEqual(meta.twitter.images, []);
  }
});
