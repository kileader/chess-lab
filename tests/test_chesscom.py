from datetime import date
from pathlib import Path

import httpx
import pytest

from chesslab import chesscom
from chesslab.openings import OpeningCatalog


CATALOG = OpeningCatalog.from_directory(Path(__file__).resolve().parents[1] / 'data' / 'openings')
PGN = (Path(__file__).parent / 'fixtures' / 'normal_game.pgn').read_text()


def entry(game_id=1, **changes):
    return {'url': f'https://www.chess.com/game/live/{game_id}', 'rules': 'chess',
            'time_class': 'rapid', 'end_time': 1787788800,  # 2026-08-27 00:00 UTC
            'pgn': PGN.replace('[Site "Local"]', '[Site "Chess.com"]').replace('[Round "1"]', f'[Round "{game_id}"]'), **changes}


def records(monkeypatch, games, time_class='rapid'):
    monkeypatch.setattr(chesscom, 'fetch_json', lambda path: {'games': games})
    return chesscom.monthly_records('Alice', '2026-08', date(2026, 8, 27), date(2026, 8, 27), time_class, CATALOG)


def test_archive_plan_only_uses_valid_months_and_never_provider_urls(monkeypatch):
    calls = []
    def fetch(path):
        calls.append(path)
        return {'archives': [f'{chesscom.API_ROOT}/alice/games/{month}' for month in ['2026/07', '2026/08', '2026/08', '2025/12']]}
    monkeypatch.setattr(chesscom, 'fetch_json', fetch)
    assert chesscom.archive_months('ALICE', date(2026, 7, 15), date(2026, 8, 30)) == ['2026-08', '2026-07']
    assert calls == ['alice/games/archives']
    for address in ['http://127.0.0.1/secrets', f'{chesscom.API_ROOT}/bob/games/2026/08',
                    f'{chesscom.API_ROOT}/alice/games/2026/08?redirect=secret',
                    f'{chesscom.API_ROOT}/alice/games/2026/99']:
        monkeypatch.setattr(chesscom, 'fetch_json', lambda path: {'archives': [address]})
        with pytest.raises(chesscom.ChessComError, match='invalid archive address'):
            chesscom.archive_months('Alice', date(2026, 1, 1), date(2026, 8, 30))


def test_month_filters_end_dates_speed_and_variants_and_sets_source(monkeypatch):
    games = [entry(), entry(2, time_class='blitz'), entry(3, rules='chess960'),
             entry(4, end_time=1787788799), entry(5, end_time=1787875200),
             entry(6, end_time=1787875199)]
    found, filtered = records(monkeypatch, games)
    assert [record.source_game_id for record in found] == ['1', '6']
    assert filtered == 4
    assert all(record.source == 'chess_com' and record.white == 'Alice' for record in found)
    assert len(records(monkeypatch, games, 'all')[0]) == 3
    assert records(monkeypatch, [], 'rapid') == ([], 0)


@pytest.mark.parametrize('bad', [
    {'pgn': ''}, {'pgn': PGN + '\n\n' + PGN}, {'pgn': PGN.replace('Alice', 'SomeoneElse')},
    {'pgn': PGN.replace('1-0', '*')}, {'pgn': '[Result "1-0"]\n\n1. e4 e5 2. Ke8 1-0'},
    {'url': 'https://evil.example/game/live/1'}, {'end_time': 'yesterday'},
])
def test_invalid_game_rejects_entire_month(monkeypatch, bad):
    with pytest.raises(chesscom.ChessComError, match='No games from this month were saved'):
        records(monkeypatch, [entry(), entry(2, **bad)])


def test_month_size_and_game_count_bounds(monkeypatch):
    monkeypatch.setattr(chesscom, 'MAX_MONTH_GAMES', 1)
    with pytest.raises(chesscom.ChessComError) as error:
        records(monkeypatch, [entry(), entry(2)])
    assert error.value.status_code == 413


@pytest.mark.parametrize('status, expected', [(404, 404), (410, 404), (429, 429), (403, 502), (500, 502), (302, 502)])
def test_upstream_errors_are_safe_and_release_serial_lock(monkeypatch, status, expected):
    real_client = httpx.Client
    calls = []
    def respond(request):
        calls.append(request)
        assert 'authorization' not in request.headers
        assert 'cookie' not in request.headers
        assert request.headers['user-agent'].startswith('ChessLab/')
        return httpx.Response(status, headers={'Location': 'http://127.0.0.1/private'}, text='secret upstream body')
    monkeypatch.setattr(chesscom.httpx, 'Client', lambda **kwargs: real_client(transport=httpx.MockTransport(respond), **kwargs))
    with pytest.raises(chesscom.ChessComError) as error:
        chesscom.fetch_json('alice/games/archives')
    assert error.value.status_code == expected
    assert 'secret' not in str(error.value)
    assert len(calls) == 1
    assert not chesscom._request_lock.locked()


def test_network_timeout_oversize_and_invalid_json(monkeypatch):
    real_client = httpx.Client
    def timeout(request):
        raise httpx.ReadTimeout('timeout')
    for handler, expected in [(timeout, 504), (lambda request: httpx.Response(200, content=b'x' * 11), 413),
                              (lambda request: httpx.Response(200, content=b'not json'), 502)]:
        monkeypatch.setattr(chesscom, 'MAX_BYTES', 10)
        monkeypatch.setattr(chesscom.httpx, 'Client', lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
        with pytest.raises(chesscom.ChessComError) as error:
            chesscom.fetch_json('alice/games/archives')
        assert error.value.status_code == expected
        assert not chesscom._request_lock.locked()


def test_parallel_request_is_rejected_without_network():
    with chesscom._request_lock:
        with pytest.raises(chesscom.ChessComError) as error:
            chesscom.fetch_json('alice/games/archives')
        assert error.value.status_code == 429
