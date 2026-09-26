export type OpeningResult = {
  eco: string | null;
  opening: string;
  games: number;
  wins: number;
  draws: number;
  losses: number;
  moves: string[];
};

export type PracticeTarget = OpeningResult & {
  color: 'white' | 'black';
  score: number;
  family: string;
  representativeGames: number;
  representativeOpening: string;
};

export function practiceName(opening: string, color: 'white' | 'black') {
  const name = opening.split(':').at(-1) ?? opening;
  if (color === 'black') return `As Black against ${name}`;
  return /\bDefense\b/i.test(name) ? `As White against ${name}` : `As White in ${name}`;
}

export function practiceTargetsFor(overviews: Array<{ color: 'white' | 'black'; openings: OpeningResult[] }>): PracticeTarget[] {
  const grouped = new Map<string, PracticeTarget>();
  for (const { color, openings } of overviews) {
    for (const opening of openings) {
      if (opening.moves.length < 2 || opening.opening === "Queen's Pawn Game") continue;
      // London positions have several catalog families and variation names.
      const name = /\bLondon System\b/i.test(opening.opening) ? 'London System' : opening.opening;
      const key = `${color}:${name}`;
      const existing = grouped.get(key);
      if (existing) {
        existing.games += opening.games;
        existing.wins += opening.wins;
        existing.draws += opening.draws;
        existing.losses += opening.losses;
        if (opening.games > existing.representativeGames) {
          existing.moves = opening.moves;
          existing.representativeGames = opening.games;
          existing.family = opening.opening.split(':', 1)[0];
          existing.representativeOpening = opening.opening;
        }
      } else {
        grouped.set(key, {
          ...opening, opening: name, color, score: 0,
          family: opening.opening.split(':', 1)[0], representativeGames: opening.games,
          representativeOpening: opening.opening,
        });
      }
    }
  }
  return [...grouped.values()]
    .filter((opening) => opening.games >= 8)
    .map((opening) => ({
      ...opening,
      score: ((opening.wins + opening.draws / 2) / opening.games) * 100,
    }))
    .filter((opening) => opening.score < 45)
    .sort((left, right) => left.score - right.score || right.games - left.games)
    .slice(0, 3);
}

export function practiceHref(opening: PracticeTarget, query: URLSearchParams) {
  const targetQuery = new URLSearchParams(query);
  targetQuery.set('color', opening.color);
  targetQuery.set('focus', opening.representativeOpening);
  return `/openings/${encodeURIComponent(opening.family)}?${targetQuery}#explorer`;
}
