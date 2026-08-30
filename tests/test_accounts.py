"""Private account regression tests shared by SQLite and real PostgreSQL."""
import os
from pathlib import Path
from uuid import uuid4

import httpx
import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from backend.app import app, get_storage
from backend.auth import Principal, get_principal, validate_auth_configuration
from chesslab.postgres import PostgresGameStorage, postgres_query
from chesslab.storage import SQLiteGameStorage
from backend.migrate_local import copy_library
from chesslab.importer import load_game_records


@pytest.fixture(params=['sqlite', 'postgres'])
def account_storage(request, tmp_path):
    if request.param == 'sqlite':
        yield SQLiteGameStorage(tmp_path / 'accounts.db')
        return
    url = os.getenv('CHESSLAB_TEST_POSTGRES_URL')
    if not url:
        pytest.skip('Set CHESSLAB_TEST_POSTGRES_URL to test a disposable PostgreSQL database.')
    schema = 'chesslab_test_' + uuid4().hex
    with psycopg.connect(url, autocommit=True) as connection:
        connection.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
    try:
        storage = PostgresGameStorage(make_conninfo(url, options=f'-c search_path={schema}'))
        storage.migrate()
        storage.migrate()  # Deployment retries are safe.
        yield storage
    finally:
        with psycopg.connect(url, autocommit=True) as connection:
            connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


@pytest.fixture
def accounts(account_storage, monkeypatch):
    app.dependency_overrides[get_storage] = lambda: account_storage
    def principal(request):
        token = request.headers.get('authorization', '')
        if token not in {'Bearer alice', 'Bearer bob'}:
            raise HTTPException(401, 'Sign in.')
        name = token.split()[-1]
        return Principal(name, name + '@example.test')
    monkeypatch.setattr('backend.app.get_principal', principal)
    with TestClient(app) as client:
        yield client, account_storage
    app.dependency_overrides.clear()


def test_private_accounts_cannot_claim_handles_or_see_other_imports(accounts):
    client, storage = accounts
    alice = {'Authorization': 'Bearer alice'}
    bob = {'Authorization': 'Bearer bob'}
    a = client.get('/api/account', headers=alice).json()['id']
    b = client.get('/api/account', headers=bob).json()['id']
    assert a != b
    assert client.get('/api/account', headers=alice).json()['id'] == a
    profile = {'display_name': 'Alice', 'platform': 'lichess', 'username': 'Alice'}
    assert client.post('/api/account', headers=alice, json=profile).status_code == 200
    # Entering the same public chess handle never transfers account ownership.
    assert client.post('/api/account', headers=bob, json=profile).status_code == 200
    pgn = (Path(__file__).parent / 'fixtures' / 'normal_game.pgn').read_text().replace('[Site "Local"]', '[Site "https://lichess.org/aB3dE5gH"]')
    imported = client.post('/api/games/import', headers=alice, files={'file': ('game.pgn', pgn)})
    assert imported.json()['games_added'] == 1
    assert client.get('/api/games', headers=bob).json()['total'] == 0
    assert client.get(f'/api/users/{b}/overview', headers=bob).json()['total_games'] == 0
    assert client.get(f'/api/users/{b}/openings/explorer?family=King%27s%20Pawn%20Game&color=white', headers=bob).json()['games'] == 0
    assert client.post('/api/games/import', headers=bob, files={'file': ('game.pgn', pgn)}).json()['games_added'] == 1
    assert client.post('/api/games/import', headers=bob, files={'file': ('game.pgn', pgn)}).json()['duplicates_skipped'] == 1
    assert storage.count_games() == 2
    assert client.get('/api/games', headers=bob).json()['total'] == 1
    for endpoint in ('overview', 'responses', 'openings/adjusted', 'openings/detail?family=King%27s%20Pawn%20Game', 'openings/practice?family=King%27s%20Pawn%20Game'):
        assert client.get(f'/api/users/{a}/{endpoint}', headers=alice).status_code == 200
    saved = client.post(f'/api/users/{a}/practice-positions', headers=alice, json={
        'family': "King's Pawn Game", 'player_color': 'white', 'line': ['e7e5'], 'note': 'Private thought', 'candidate_move': 'Nf3',
    }).json()['position']
    assert client.get(f'/api/users/{b}/practice-positions', headers=bob).json() == []
    assert client.patch(f'/api/users/{b}/practice-positions/{saved["id"]}', headers=bob, json={'note': 'Stolen'}).status_code == 404
    assert client.delete(f'/api/users/{b}/practice-positions/{saved["id"]}', headers=bob).status_code == 404
    assert client.get(f'/api/users/{a}/practice-positions', headers=alice).json()[0]['note'] == 'Private thought'
    plan = [{'context': 'As White', 'opening': "King's Pawn Game", 'status': 'try', 'note': 'Private plan'}]
    assert client.post(f'/api/users/{a}/repertoire', headers=alice, json=plan).status_code == 200
    assert client.get(f'/api/users/{b}/repertoire', headers=bob).json() == []
    assert client.post('/api/account', headers=alice, json={**profile, 'username': 'SomeoneElse'}).status_code == 409


def test_every_user_route_enforces_identity(accounts):
    client, storage = accounts
    a = storage.ensure_account('alice')
    storage.ensure_account('bob')
    for route in app.routes:
        if '{user_id}' not in getattr(route, 'path', ''):
            continue
        path = route.path.replace('{user_id}', str(a)).replace('{item_id}', '1').replace('{position_id}', '1')
        for method in route.methods - {'HEAD', 'OPTIONS'}:
            response = client.request(method, path, headers={'Authorization': 'Bearer bob'}, json={})
            assert response.status_code == 404, (method, path, response.text)
            assert client.request(method, path, json={}).status_code == 401
    assert client.get('/health').status_code == 200
    assert client.get('/api/users', headers={'Authorization': 'Bearer alice'}).status_code == 404
    assert client.post('/api/users', headers={'Authorization': 'Bearer alice'}, json={}).status_code == 404
    assert client.get('/api/games').status_code == 401


def test_legacy_library_not_claimed_by_new_login(accounts):
    client, storage = accounts
    legacy = storage.get_or_create_user_for_identity(display_name='Alice', platform='lichess', username='Alice')
    storage.save_repertoire_items(legacy, [{'context': 'As White', 'opening': 'Sicilian Defense', 'status': 'keep', 'note': 'Legacy note'}])
    logged_in = client.get('/api/account', headers={'Authorization': 'Bearer alice'}).json()['id']
    assert logged_in != legacy
    assert storage.get_user_repertoire(logged_in) == []
    assert storage.get_user_repertoire(legacy)[0]['note'] == 'Legacy note'


def auth_request(token=None, host='testserver', client='127.0.0.1', extra=()):
    headers = [(b'host', host.encode()), *extra]
    if token:
        headers.append((b'authorization', token.encode()))
    return Request({'type': 'http', 'method': 'GET', 'scheme': 'http', 'path': '/api/account', 'query_string': b'',
                    'headers': headers, 'client': (client, 1234), 'server': (host, 80)})


@pytest.mark.parametrize('allowed_emails', [None, '', ' , ', 'alice@example.test'])
def test_real_verifier_rejects_bad_sessions_and_checks_invites(monkeypatch, allowed_emails):
    monkeypatch.setenv('CHESSLAB_AUTH_MODE', 'supabase')
    monkeypatch.setenv('SUPABASE_URL', 'https://project.supabase.co')
    monkeypatch.setenv('SUPABASE_PUBLISHABLE_KEY', 'test-public-key')
    monkeypatch.setenv('CHESSLAB_ENV', 'production')
    if allowed_emails is None:
        monkeypatch.delenv('CHESSLAB_ALLOWED_EMAILS', raising=False)
    else:
        monkeypatch.setenv('CHESSLAB_ALLOWED_EMAILS', allowed_emails)
    validate_auth_configuration()
    subject = str(uuid4())
    def respond(request):
        assert str(request.url) == 'https://project.supabase.co/auth/v1/user'
        token = request.headers['authorization']
        if token == 'Bearer invalid':
            return httpx.Response(401)
        return httpx.Response(200, json={'id': subject, 'email': token.split()[-1] + '@example.test',
                                      'email_confirmed_at': None if token == 'Bearer unverified' else '2026-08-30T00:00:00Z',
                                      'is_anonymous': token == 'Bearer anonymous'})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        monkeypatch.setattr('backend.auth.auth_client', lambda: client)
        assert get_principal(auth_request('Bearer alice')).subject == subject
        failures = [(None, 401), ('Bearer invalid', 401), ('Bearer unverified', 401), ('Bearer anonymous', 401)]
        if allowed_emails == 'alice@example.test':
            failures.append(('Bearer bob', 403))
        else:
            assert get_principal(auth_request('Bearer bob')).email == 'bob@example.test'
        for token, code in failures:
            with pytest.raises(HTTPException) as error:
                get_principal(auth_request(token))
            assert error.value.status_code == code


def test_local_bypass_is_never_public_or_production(monkeypatch):
    monkeypatch.setenv('CHESSLAB_AUTH_MODE', 'local')
    monkeypatch.delenv('DATABASE_URL', raising=False)
    monkeypatch.delenv('RAILWAY_ENVIRONMENT_ID', raising=False)
    monkeypatch.setenv('CHESSLAB_ENV', 'development')
    assert get_principal(auth_request(host='127.0.0.1')) is None
    for request in [auth_request(host='evil.example'), auth_request(host='localhost', client='10.0.0.1'),
                    auth_request(host='localhost', extra=[(b'x-forwarded-for', b'127.0.0.1')])]:
        with pytest.raises(HTTPException):
            get_principal(request)
    monkeypatch.setenv('CHESSLAB_ENV', 'production')
    with pytest.raises(RuntimeError, match='forbidden'):
        validate_auth_configuration()


def test_postgres_binds_do_not_interpolate_or_replace_literal_question_marks():
    assert postgres_query("SELECT '?' AS literal, ? AS value, '100%' AS pct") == "SELECT '?' AS literal, %s AS value, '100%%' AS pct"


def test_library_copy_is_opt_in_transactional_and_repeatable(account_storage, tmp_path):
    source_path = tmp_path / 'legacy.db'
    source = SQLiteGameStorage(source_path)
    legacy = source.get_or_create_user_for_identity(display_name='Alice', platform='lichess', username='Alice')
    record = load_game_records(Path(__file__).parent / 'fixtures' / 'normal_game.pgn')[0]
    # Fixture uses a local site; establish the original selected user's link explicitly.
    source.save_games([record])
    with source._connect() as connection:
        connection.execute("INSERT INTO user_games(user_id, game_id, player_color) VALUES (?, 1, 'white')", (legacy,))
    source.save_repertoire_items(legacy, [{'context': 'As White', 'opening': 'Sicilian Defense', 'status': 'keep', 'note': 'Original note'}])
    expected = {'games': 1, 'repertoire_items': 1, 'practice_positions': 0}
    assert copy_library(source_path, legacy) == expected
    with pytest.raises(ValueError, match='Destination account not found'):
        copy_library(source_path, legacy, account_storage, 'missing')
    dest = account_storage.ensure_account('alice')
    assert copy_library(source_path, legacy, account_storage, 'alice') == expected
    assert copy_library(source_path, legacy, account_storage, 'alice') == expected
    assert account_storage.count_games(owner_user_id=dest) == 1
    assert account_storage.get_user_repertoire(dest)[0]['note'] == 'Original note'
    account_storage.save_repertoire_items(dest, [{'context': 'As White', 'opening': 'Sicilian Defense', 'status': 'try', 'note': 'Newer note'}])
    copy_library(source_path, legacy, account_storage, 'alice')
    assert account_storage.get_user_repertoire(dest)[0]['note'] == 'Newer note'
    assert source.count_games() == 1


def test_upload_limits_and_onboarding(accounts):
    client, storage = accounts
    headers = {'Authorization': 'Bearer alice'}
    assert client.post('/api/games/import', headers=headers, files={'file': ('game.pgn', '1. e4 *')}).status_code == 409
    assert client.post('/api/games/import', headers={**headers, 'Content-Length': str(12 * 1024 * 1024)}, content=b'large').status_code == 413
    profile = {'display_name': 'Alice', 'platform': 'lichess', 'username': 'Alice'}
    assert client.post('/api/account', headers=headers, json=profile).status_code == 200
    assert client.post('/api/games/import', headers=headers, files={'file': ('large.pgn', b'x' * (10 * 1024 * 1024 + 1))}).status_code == 413
    assert storage.count_games() == 0
