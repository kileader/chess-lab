const pieces: Record<string, string> = { K: '♔', Q: '♕', R: '♖', B: '♗', N: '♘', P: '♙', k: '♚', q: '♛', r: '♜', b: '♝', n: '♞', p: '♟' };
const pieceNames: Record<string, string> = { k: 'king', q: 'queen', r: 'rook', b: 'bishop', n: 'knight', p: 'pawn' };

export function ChessBoard({ fen, color }: { fen: string; color: 'white' | 'black' }) {
  const squares = fen.split(' ')[0].split('/').flatMap((rank) => [...rank].flatMap((symbol) => /[1-8]/.test(symbol) ? Array(Number(symbol)).fill('') as string[] : [symbol]));
  const order = Array.from({ length: 64 }, (_, index) => color === 'white' ? index : 63 - index);
  return <div className="explorer-board" role="img" aria-label={`Current chess position, ${color} at the bottom. ${squares.map((piece, index) => piece ? `${piece === piece.toUpperCase() ? 'White' : 'Black'} ${pieceNames[piece.toLowerCase()]} on ${'abcdefgh'[index % 8]}${8 - Math.floor(index / 8)}` : '').filter(Boolean).join(', ')}`}>
    {order.map((index, displayIndex) => <span className={`explorer-square ${(Math.floor(index / 8) + index % 8) % 2 ? 'square-dark' : 'square-light'}`} key={index} aria-hidden="true">
      <span className={squares[index] === squares[index].toUpperCase() ? 'piece-white' : 'piece-black'}>{pieces[squares[index]] ?? ''}</span>
      {displayIndex % 8 === 0 && <i className="rank-label">{8 - Math.floor(index / 8)}</i>}
      {displayIndex >= 56 && <i className="file-label">{'abcdefgh'[index % 8]}</i>}
    </span>)}
  </div>;
}
