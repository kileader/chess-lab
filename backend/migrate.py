"""Run idempotent, transactional PostgreSQL migrations before a deployment."""
import os
from chesslab.postgres import PostgresGameStorage

if __name__ == "__main__":
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL is required. No database was changed.")
    PostgresGameStorage(url).migrate()
    print("Database migrations complete.")
