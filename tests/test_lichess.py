from datetime import date
from pathlib import Path
import json

import httpx
import pytest

from chesslab import lichess
from chesslab.openings import OpeningCatalog


CATALOG = OpeningCatalog.from_directory(Path(__file__).resolve().parents[1] / 'data' / 'openings')
PGN = (Path(__file__).parent / 'fixtures' / 'normal_game.pgn').read_text()
START = 1787788800000


def entry(game_id='aB3dE5gH', **changes):
    return {'id': game_id, 'createdAt': START, 'status': 'mate', 'variant': 'standard', 'perf': 'rapid',
            'pgn': PGN.replace('[Site "Local"]', f'[Site "https://lichess.org/{game_id}"]'), **changes}


def mock_http(monkeypatch, respond):
    real_client = httpx.Client
    monkeypatch.setattr(lichess.httpx, 'Client', lambda **kwargs: real_client(transport=httpx.MockTransport(respond), **kwargs))
    monkeypatch.setattr(lichess, '_retry_after', 0)


def test_export_is_bounded_unauthenticated_and_uses_direct_timestamp_query(monkeypatch):
    def respond(request):
        assert request.url.host == 'lichess.org'
        assert request.url.path == '/api/games/user/alice'
        assert 'authorization' not in request.headers and 'cookie' not in request.headers
        assert request.headers['accept'] == 'application/x-ndjson'
        assert 'perfType' not in request.url.params  # Search index is not used.
        assert request.url.params['ongoing'] == 'false'
        assert request.url.params['max'] == str(lichess.BATCH_SIZE + 1)
        assert request.url.params['until'] == str(START + 1)
        return httpx.Response(200, content='\n' + json.dumps(entry()) + '\n\n')
    mock_http(monkeypatch, respond)
    found = lichess.export_games('ALICE', START, START + 1, 'rapid')
    assert len(found) == 1
    assert not lichess._request_lock.locked()


def test_months_and_utc_bounds(monkeypatch):
    monkeypatch.setattr(lichess, 'export_games', lambda *args, **kwargs: [entry()])
    assert lichess.archive_months('Alice', date(2026, 1, 1), date(2026, 8, 30), 'rapid') == ['2026-08']
    assert lichess.month_bounds('2026-08', date(2026, 8, 27), date(2026, 8, 27)) == (START, START + 86400000)
    assert lichess.month_bounds('2024-02', date(2024, 1, 1), date(2024, 12, 31))[1] == lichess.date_bounds(date(2024, 3, 1), date(2024, 3, 1))[0]
    monkeypatch.setattr(lichess, 'export_games', lambda *args, **kwargs: [])
    assert lichess.archive_months('Alice', date(2026, 1, 1), date(2026, 8, 30), 'rapid') == []


def test_large_windows_split_before_saving_and_cover_tied_timestamps(monkeypatch):
    monkeypatch.setattr(lichess, 'BATCH_SIZE', 2)
    games = [entry('00000001', createdAt=START), entry('00000002', createdAt=START + 5), entry('00000003', createdAt=START + 5)]
    monkeypatch.setattr(lichess, 'export_games', lambda user, since, until, speed: [g for g in games if since <= g['createdAt'] < until])
    records, filtered, windows = lichess.batch_records('Alice', START, START + 10, 'rapid', CATALOG)
    assert records == [] and filtered == 0
    assert windows == [{'since': START, 'until': START + 5}, {'since': START + 5, 'until': START + 10}]
    ids = []
    for window in windows:
        found, _, more = lichess.batch_records('Alice', window['since'], window['until'], 'rapid', CATALOG)
        assert more == []
        ids.extend(g.source_game_id for g in found)
    assert ids == ['00000001', '00000002', '00000003']
    monkeypatch.setattr(lichess, 'export_games', lambda *args: games)
    with pytest.raises(lichess.LichessError, match='share one timestamp'):
        lichess.batch_records('Alice', START, START + 1, 'rapid', CATALOG)


def test_filters_speed_variant_unfinished_and_preserves_source(monkeypatch):
    games = [entry(), entry('00000002', perf='blitz'), entry('00000003', variant='chess960'), entry('00000004', status='started')]
    monkeypatch.setattr(lichess, 'export_games', lambda *args: games)
    records, filtered, windows = lichess.batch_records('Alice', START, START + 1, 'rapid', CATALOG)
    assert len(records) == 1 and filtered == 3 and windows == []
    assert records[0].source == 'lichess' and records[0].source_game_id == 'aB3dE5gH'
    assert records[0].source_url == 'https://lichess.org/aB3dE5gH'
    assert len(lichess.batch_records('Alice', START, START + 1, 'all', CATALOG)[0]) == 2


@pytest.mark.parametrize('changes', [{'id': '../evil'}, {'pgn': ''}, {'pgn': PGN + '\n\n' + PGN},
                                    {'pgn': PGN.replace('Alice', 'OtherPlayer')}, {'pgn': PGN.replace('1-0', '*')}])
def test_bad_games_abort_batch(monkeypatch, changes):
    monkeypatch.setattr(lichess, 'export_games', lambda *args: [entry(), entry(**changes)])
    with pytest.raises(lichess.LichessError, match='No games from this batch were saved'):
        lichess.batch_records('Alice', START, START + 1, 'rapid', CATALOG)


@pytest.mark.parametrize('status, expected', [(404, 404), (429, 429), (403, 502), (500, 502), (302, 502)])
def test_http_errors_no_redirects_and_no_raw_body_leak(monkeypatch, status, expected):
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(status, headers={'Location': 'http://127.0.0.1/private'}, text='secret response')
    mock_http(monkeypatch, respond)
    with pytest.raises(lichess.LichessError) as error:
        lichess.export_games('Alice', START, START + 1, 'rapid')
    assert error.value.status_code == expected
    assert 'secret' not in str(error.value)
    assert not lichess._request_lock.locked()
    if status == 429:
        with pytest.raises(lichess.LichessError):
            lichess.export_games('Alice', START, START + 1, 'rapid')
    assert len(calls) == 1


def test_stream_limits_timeout_invalid_dates_and_json(monkeypatch):
    def timeout(request):
        raise httpx.ReadTimeout('timeout')
    for respond, expected in [(timeout, 504), (lambda request: httpx.Response(200, content=b'x' * (lichess.MAX_BYTES + 1)), 413),
                              (lambda request: httpx.Response(200, text='not json'), 502),
                              (lambda request: httpx.Response(200, text=json.dumps(entry(createdAt=START + 1))), 502)]:
        with monkeypatch.context() as patch:
            mock_http(patch, respond)
            with pytest.raises(lichess.LichessError) as error:
                lichess.export_games('Alice', START, START + 1, 'rapid')
            assert error.value.status_code == expected
            assert not lichess._request_lock.locked()


def test_parallel_exports_rejected_without_network():
    with lichess._request_lock:
        with pytest.raises(lichess.LichessError) as error:
            lichess.export_games('Alice', START, START + 1, 'rapid')
        assert error.value.status_code == 429
