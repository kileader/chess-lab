"""FastAPI application for Chess Lab."""

import os
from io import TextIOWrapper
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict

from chesslab import APP_NAME
from chesslab.importer import iter_game_records
from chesslab.models import GameRecord
from chesslab.openings import OpeningCatalog
from chesslab.storage import SQLiteGameStorage


class ImportResponse(BaseModel):
    """Compact summary returned after a PGN import."""

    games_received: int
    games_added: int
    duplicates_skipped: int


class GameSummary(BaseModel):
    """Stored game metadata returned without the potentially large PGN body."""

    model_config = ConfigDict(from_attributes=True)

    date: str | None
    white: str | None
    black: str | None
    white_elo: int | None
    black_elo: int | None
    result: str | None
    time_control: str | None
    eco: str | None
    opening: str | None
    opening_ply: int | None
    move_count: int
    site: str | None
    source: str
    source_url: str | None
    source_game_id: str | None


class GamePage(BaseModel):
    """One bounded page of stored game summaries."""

    total: int
    limit: int
    offset: int
    games: list[GameSummary]


class PlayerIdentity(BaseModel):
    """One chess-platform account belonging to an app user."""

    platform: str
    username: str


class UserProfile(BaseModel):
    """An app user with one or more chess-platform identities."""

    id: int
    display_name: str
    identities: list[PlayerIdentity]


class CreateUserRequest(BaseModel):
    """Details needed to establish a platform-linked user profile."""

    display_name: str
    platform: str
    username: str


class OpeningOverview(BaseModel):
    """A user's results in one classified opening."""

    eco: str | None
    opening: str
    games: int
    wins: int
    draws: int
    losses: int


class UserOverview(BaseModel):
    """High-level chess statistics calculated from one user's perspective."""

    user: UserProfile
    total_games: int
    white_games: int
    black_games: int
    wins: int
    draws: int
    losses: int
    classified_games: int
    first_game_date: str | None
    last_game_date: str | None
    minimum_rating: int | None
    maximum_rating: int | None
    top_openings: list[OpeningOverview]


class ResultBreakdown(BaseModel):
    """Perspective-aware results for one slice of an opening family."""

    games: int
    wins: int
    draws: int
    losses: int


class ColorBreakdown(ResultBreakdown):
    color: str


class OpeningVariation(ResultBreakdown):
    eco: str | None
    opening: str


class YearBreakdown(ResultBreakdown):
    year: str


class OpeningGame(BaseModel):
    date: str | None
    white: str | None
    black: str | None
    result: str | None
    time_control: str | None
    eco: str | None
    opening: str | None
    source_url: str | None
    player_color: str


class OpeningDetail(ResultBreakdown):
    """One opening family analyzed from a user's perspective."""

    user: UserProfile
    family: str
    colors: list[ColorBreakdown]
    variations: list[OpeningVariation]
    years: list[YearBreakdown]
    recent_games: list[OpeningGame]


app = FastAPI(title=APP_NAME)
allowed_origins = os.environ.get(
    "CHESSLAB_ALLOWED_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000",
).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in allowed_origins if origin.strip()],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
default_storage = SQLiteGameStorage(
    Path(os.environ.get("CHESSLAB_DATABASE_PATH", "data/chesslab.db"))
)
default_opening_catalog = OpeningCatalog.from_directory(
    Path(__file__).resolve().parents[1] / "data" / "openings"
)


def get_storage() -> SQLiteGameStorage:
    """Provide the configured game storage to API routes."""
    return default_storage


StorageDependency = Annotated[SQLiteGameStorage, Depends(get_storage)]


@app.get("/health")
def health() -> dict[str, str]:
    """Report whether the API process is running."""
    return {"status": "ok"}


@app.post("/api/games/import")
async def import_games(
    file: UploadFile,
    storage: StorageDependency,
) -> ImportResponse:
    """Parse and persist an uploaded PGN file, then return its game records."""
    await file.seek(0)
    pgn_stream = TextIOWrapper(file.file, encoding="utf-8-sig")
    try:
        games_received, games_added = storage.import_games(
            iter_game_records(pgn_stream, default_opening_catalog)
        )
    except UnicodeDecodeError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="PGN file must contain UTF-8 text.",
        ) from error
    finally:
        pgn_stream.detach()

    return ImportResponse(
        games_received=games_received,
        games_added=games_added,
        duplicates_skipped=games_received - games_added,
    )


@app.get("/api/games", response_model=GamePage)
def list_games(
    storage: StorageDependency,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> GamePage:
    """Return a bounded page of stored games in import order."""
    games = storage.list_games(limit=limit, offset=offset)
    return GamePage(
        total=storage.count_games(),
        limit=limit,
        offset=offset,
        games=[GameSummary.model_validate(game) for game in games],
    )


@app.post("/api/users", response_model=UserProfile)
def create_user(request: CreateUserRequest, storage: StorageDependency) -> UserProfile:
    """Create an app user for a Lichess or Chess.com identity."""
    if request.platform not in {"lichess", "chess_com"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Platform must be 'lichess' or 'chess_com'.",
        )
    try:
        user_id = storage.get_or_create_user_for_identity(
            display_name=request.display_name,
            platform=request.platform,
            username=request.username,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error
    profile = storage.get_user_profile(user_id)
    return UserProfile.model_validate(profile)


@app.get("/api/users", response_model=list[UserProfile])
def list_users(storage: StorageDependency) -> list[UserProfile]:
    """Return all local app users and their platform identities."""
    return [UserProfile.model_validate(profile) for profile in storage.list_user_profiles()]


@app.get("/api/users/{user_id}/overview", response_model=UserOverview)
def user_overview(
    user_id: int,
    storage: StorageDependency,
    date_from: Annotated[str | None, Query(pattern=r"^\d{4}\.\d{2}\.\d{2}$")] = None,
    date_to: Annotated[str | None, Query(pattern=r"^\d{4}\.\d{2}\.\d{2}$")] = None,
    color: Literal["white", "black"] | None = None,
    grouping: Literal["family", "variation"] = "family",
) -> UserOverview:
    """Return high-level statistics from the selected user's perspective."""
    overview = storage.get_user_overview(
        user_id,
        date_from=date_from,
        date_to=date_to,
        color=color,
        grouping=grouping,
    )
    if overview is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )
    return UserOverview.model_validate(overview)


@app.get("/api/users/{user_id}/openings/detail", response_model=OpeningDetail)
def user_opening_detail(
    user_id: int,
    storage: StorageDependency,
    family: Annotated[str, Query(min_length=1, max_length=160)],
    date_from: Annotated[str | None, Query(pattern=r"^\d{4}\.\d{2}\.\d{2}$")] = None,
    date_to: Annotated[str | None, Query(pattern=r"^\d{4}\.\d{2}\.\d{2}$")] = None,
    color: Literal["white", "black"] | None = None,
) -> OpeningDetail:
    """Analyze one opening family by color, variation, year, and recent games."""
    detail = storage.get_user_opening_detail(
        user_id, family, date_from=date_from, date_to=date_to, color=color
    )
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User or opening family not found.",
        )
    return OpeningDetail.model_validate(detail)
