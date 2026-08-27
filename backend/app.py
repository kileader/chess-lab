"""FastAPI application for Chess Lab."""

from fastapi import FastAPI, HTTPException, UploadFile, status
from pydantic import BaseModel

from chesslab import APP_NAME
from chesslab.importer import parse_game_records
from chesslab.models import GameRecord


class ImportResponse(BaseModel):
    """JSON returned after a PGN import."""

    games_loaded: int
    games: list[GameRecord]


app = FastAPI(title=APP_NAME)


@app.get("/health")
def health() -> dict[str, str]:
    """Report whether the API process is running."""
    return {"status": "ok"}


@app.post("/api/games/import")
async def import_games(file: UploadFile) -> ImportResponse:
    """Parse an uploaded PGN file and return structured game records."""
    contents = await file.read()

    try:
        pgn_text = contents.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="PGN file must contain UTF-8 text.",
        ) from error

    records = parse_game_records(pgn_text)
    return ImportResponse(games_loaded=len(records), games=records)
