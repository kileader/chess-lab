'use client';

import { useState } from 'react';
import { ChessBoard } from '../../../chess-board';

export function Replay({ positions, moves }: { positions: string[]; moves: string[] }) {
  const [ply, setPly] = useState(0);
  const [color, setColor] = useState<'white' | 'black'>('white');
  return <section className="community-replay" aria-label="Game replay"><div>
    <ChessBoard fen={positions[ply]} color={color} />
    <div className="community-replay-controls">
      <button disabled={ply === 0} onClick={() => setPly(0)}>Start</button>
      <button disabled={ply === 0} onClick={() => setPly(ply - 1)}>Previous</button>
      <button disabled={ply === moves.length} onClick={() => setPly(ply + 1)}>Next</button>
      <button disabled={ply === moves.length} onClick={() => setPly(moves.length)}>End</button>
      <button onClick={() => setColor(color === 'white' ? 'black' : 'white')}>Flip board</button>
    </div><p role="status">{ply === 0 ? 'Starting position' : moves[ply - 1]} · {ply} / {moves.length} half-moves</p>
  </div><div className="community-moves" aria-label="Move list">
    {moves.map((move, index) => <button key={index} aria-current={ply === index + 1 ? 'step' : undefined} onClick={() => setPly(index + 1)}>{move}</button>)}
    {!moves.length && <p>No moves recorded.</p>}
  </div></section>;
}
