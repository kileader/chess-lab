import assert from 'node:assert/strict';
import test from 'node:test';
import { practiceHref, practiceName, practiceTargetsFor } from '../lib/practice-targets.ts';

function result(opening, moves, games, wins = 0, draws = 0) {
  return { eco: null, opening, moves, games, wins, draws, losses: games - wins - draws };
}

test('recommends a color-specific London pattern across catalog families', () => {
  const targets = practiceTargetsFor([
    { color: 'black', openings: [
      result("Queen's Pawn Game", ['d4'], 31, 10),
      result('Indian Defense: Accelerated London System', ['d4', 'Nf6', 'Bf4'], 6, 1),
      result("Queen's Pawn Game: London System", ['d4', 'd5', 'Nf3', 'Nf6', 'Bf4'], 4, 1),
    ] },
    { color: 'white', openings: [
      result("Queen's Pawn Game: London System", ['d4', 'd5', 'Nf3', 'Nf6', 'Bf4'], 12, 2),
    ] },
  ]);

  assert.equal(targets.length, 2);
  const black = targets.find((target) => target.color === 'black');
  assert.equal(black.opening, 'London System');
  assert.equal(black.games, 10);
  assert.equal(black.score, 20);
  assert.equal(black.family, 'Indian Defense');
  assert.equal(practiceName(black.opening, black.color), 'As Black against London System');
  const href = practiceHref(black, new URLSearchParams('date_from=2026.08.27'));
  assert.match(href, /^\/openings\/Indian%20Defense\?/);
  assert.equal(new URL(href, 'http://localhost').searchParams.get('focus'), 'Indian Defense: Accelerated London System');
  assert.equal(new URL(href, 'http://localhost').searchParams.get('color'), 'black');
});

test('does not recommend a one-move bucket or a thin named sample', () => {
  assert.deepEqual(practiceTargetsFor([{ color: 'black', openings: [
    result("Queen's Pawn Game", ['d4'], 40),
    result('London System', ['d4', 'Nf6', 'Nf3', 'g6', 'Bf4'], 7),
  ] }]), []);
});
