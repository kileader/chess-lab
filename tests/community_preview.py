"""Disposable public-record fixture for HTTP rendering checks, never real accounts.

Run `python tests/community_preview.py` with PYTHONPATH set to the repository root.
Point a separate frontend process at http://127.0.0.1:8001. Stop with Ctrl+C.
"""

from pathlib import Path
from tempfile import TemporaryDirectory

import uvicorn

from backend.app import app, get_storage
from chesslab.importer import load_game_records
from chesslab.social import CommunityStorage
from chesslab.storage import SQLiteGameStorage


def main():
    with TemporaryDirectory(prefix='chesslab-community-preview-') as directory:
        storage = SQLiteGameStorage(Path(directory) / 'preview.db')
        owner = storage.ensure_account('synthetic-preview-only')
        record = load_game_records(Path(__file__).parent / 'fixtures' / 'normal_game.pgn')[0]
        storage.import_games([record], owner_user_id=owner)
        social = CommunityStorage(storage)
        profile = social.save_profile(owner, 'Preview player', 'Synthetic profile for rendering checks.', True)
        game_id = social.library(owner, 1, 0)['games'][0]['id']
        share = social.share(owner, game_id, 'A short checkmate. <script>not executable</script>')
        app.dependency_overrides[get_storage] = lambda: storage
        print(f'PROFILE_ID={profile["public_id"]}', flush=True)
        print(f'SHARE_ID={share["public_id"]}', flush=True)
        try:
            uvicorn.run(app, host='127.0.0.1', port=8001, proxy_headers=False)
        finally:
            app.dependency_overrides.clear()


if __name__ == '__main__':
    main()
