"""FastAPI application for Chess Lab."""

import os
from io import TextIOWrapper
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import quote

from fastapi import Depends, FastAPI, HTTPException, Query, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict

from chesslab import APP_NAME
from chesslab.importer import iter_game_records
from chesslab.models import GameRecord
from chesslab.openings import OpeningCatalog
from chesslab.storage import SQLiteGameStorage
from chesslab.theory import assess_pgn_opening, first_major_mistake, opening_move_path


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


class AdjustedOpening(BaseModel):
    """An opening score normalized for the ratings faced in its games."""

    eco: str | None
    opening: str
    color: Literal["white", "black"]
    games: int
    actual_score: float
    expected_score: float
    adjusted_score: float
    confidence_low: float
    confidence_high: float
    reliability: Literal["limited", "reliable"]


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


class FirstMoveResponse(ResultBreakdown):
    reply: str


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


class OpeningTheory(BaseModel):
    family: str
    reference_opening: str
    opening_ply: int
    white_centipawns: int
    player_centipawns: int
    verdict: str


class OpeningReview(BaseModel):
    date: str | None
    white: str | None
    black: str | None
    source_url: str | None
    move: str | None
    move_number: int | None
    centipawns_lost: int | None


class TacticExample(BaseModel):
    date: str | None
    white: str | None
    black: str | None
    source_url: str | None
    move: str | None
    best_move: str | None


class TacticPattern(BaseModel):
    pattern: str
    count: int
    examples: list[TacticExample]


class TacticsOverview(BaseModel):
    sample_size: int
    patterns: list[TacticPattern]


class OpeningPractice(BaseModel):
    reference_opening: str
    moves: list[str]
    lichess_url: str


class RepertoireItemInput(BaseModel):
    context: str
    opening: str
    status: Literal["keep", "practice", "try"]
    note: str = ""


class RepertoireItem(RepertoireItemInput):
    id: int


app = FastAPI(title=APP_NAME)
allowed_origins = os.environ.get(
    "CHESSLAB_ALLOWED_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000",
).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in allowed_origins if origin.strip()],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
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


@app.get("/api/users/{user_id}/repertoire", response_model=list[RepertoireItem])
def user_repertoire(user_id: int, storage: StorageDependency) -> list[RepertoireItem]:
    """Return the selected user's saved opening plan."""
    items = storage.get_user_repertoire(user_id)
    if items is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return [RepertoireItem.model_validate(item) for item in items]


@app.post("/api/users/{user_id}/repertoire", response_model=list[RepertoireItem])
def save_user_repertoire(
    user_id: int,
    items: list[RepertoireItemInput],
    storage: StorageDependency,
) -> list[RepertoireItem]:
    """Save one or more entries in the selected user's opening plan."""
    saved = storage.save_repertoire_items(
        user_id, [item.model_dump() for item in items]
    )
    if saved is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return [RepertoireItem.model_validate(item) for item in saved]


@app.patch("/api/users/{user_id}/repertoire/{item_id}", response_model=RepertoireItem)
def update_user_repertoire_item(
    user_id: int,
    item_id: int,
    item: RepertoireItemInput,
    storage: StorageDependency,
) -> RepertoireItem:
    """Update one entry in the selected user's opening plan."""
    saved = storage.update_repertoire_item(user_id, item_id, item.model_dump())
    if saved is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repertoire entry not found.")
    return RepertoireItem.model_validate(saved)


@app.delete("/api/users/{user_id}/repertoire/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user_repertoire_item(
    user_id: int,
    item_id: int,
    storage: StorageDependency,
) -> None:
    """Delete one entry from the selected user's opening plan."""
    if not storage.delete_repertoire_item(user_id, item_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repertoire entry not found.")


@app.get("/api/users/{user_id}/overview", response_model=UserOverview)
def user_overview(
    user_id: int,
    storage: StorageDependency,
    date_from: Annotated[str | None, Query(pattern=r"^\d{4}\.\d{2}\.\d{2}$")] = None,
    date_to: Annotated[str | None, Query(pattern=r"^\d{4}\.\d{2}\.\d{2}$")] = None,
    color: Literal["white", "black"] | None = None,
    grouping: Literal["family", "variation"] = "family",
    opening_limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> UserOverview:
    """Return high-level statistics from the selected user's perspective."""
    overview = storage.get_user_overview(
        user_id,
        date_from=date_from,
        date_to=date_to,
        color=color,
        grouping=grouping,
        opening_limit=opening_limit,
    )
    if overview is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )
    return UserOverview.model_validate(overview)


@app.get("/api/users/{user_id}/openings/adjusted", response_model=list[AdjustedOpening])
def user_adjusted_openings(
    user_id: int,
    storage: StorageDependency,
    date_from: Annotated[str | None, Query(pattern=r"^\d{4}\.\d{2}\.\d{2}$")] = None,
    date_to: Annotated[str | None, Query(pattern=r"^\d{4}\.\d{2}\.\d{2}$")] = None,
    color: Literal["white", "black"] | None = None,
    grouping: Literal["family", "variation"] = "family",
    min_games: Annotated[int, Query(ge=2, le=100)] = 8,
) -> list[AdjustedOpening]:
    """Compare actual opening score with Elo-based expected score.

    This is descriptive, not a measure of objective opening strength or a causal
    claim: it only adjusts each game for the rating gap between the players.
    """
    openings = storage.get_user_adjusted_openings(
        user_id,
        date_from=date_from,
        date_to=date_to,
        color=color,
        grouping=grouping,
        min_games=min_games,
    )
    if openings is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return [AdjustedOpening.model_validate(opening) for opening in openings]


@app.get("/api/users/{user_id}/responses", response_model=list[FirstMoveResponse])
def user_first_move_responses(
    user_id: int,
    storage: StorageDependency,
    first_move: Annotated[str, Query(min_length=2, max_length=12)] = "e4",
    date_from: Annotated[str | None, Query(pattern=r"^\d{4}\.\d{2}\.\d{2}$")] = None,
    date_to: Annotated[str | None, Query(pattern=r"^\d{4}\.\d{2}\.\d{2}$")] = None,
    color: Literal["white", "black"] | None = None,
) -> list[FirstMoveResponse]:
    """Show how opponents reply to a user's first White move."""
    if storage.get_user_profile(user_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return [
        FirstMoveResponse.model_validate(response)
        for response in storage.get_user_responses_to_first_move(
            user_id, first_move, date_from=date_from, date_to=date_to, color=color
        )
    ]


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


@app.get("/api/users/{user_id}/openings/theory", response_model=OpeningTheory)
def user_opening_theory(
    user_id: int,
    storage: StorageDependency,
    family: Annotated[str, Query(min_length=1, max_length=160)],
    date_from: Annotated[str | None, Query(pattern=r"^\d{4}\.\d{2}\.\d{2}$")] = None,
    date_to: Annotated[str | None, Query(pattern=r"^\d{4}\.\d{2}\.\d{2}$")] = None,
    color: Literal["white", "black"] | None = None,
) -> OpeningTheory:
    """Evaluate a representative classified opening position with local Stockfish."""
    reference = storage.get_opening_reference_game(
        user_id, family, date_from=date_from, date_to=date_to, color=color
    )
    if reference is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opening not found.")
    assessment = assess_pgn_opening(
        str(reference["pgn"]),
        reference["opening_ply"] if isinstance(reference["opening_ply"], int) else None,
        str(reference["player_color"]),
    )
    if assessment is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Stockfish is unavailable.")
    return OpeningTheory(
        family=family,
        reference_opening=str(reference["opening"]),
        **assessment,
    )


@app.get("/api/users/{user_id}/openings/review", response_model=list[OpeningReview])
def user_opening_review(user_id: int, storage: StorageDependency, family: str, date_from: str | None = None, date_to: str | None = None, color: Literal["white", "black"] | None = None) -> list[OpeningReview]:
    """Analyze three recent losses in an opening and identify first large mistakes."""
    reviews = []
    for game in storage.get_recent_opening_losses(user_id, family, date_from=date_from, date_to=date_to, color=color):
        mistake = first_major_mistake(str(game.pop("pgn")), str(game.pop("player_color")))
        reviews.append({**game, **(mistake or {"move": None, "move_number": None, "centipawns_lost": None})})
    return reviews


@app.get("/api/users/{user_id}/openings/practice", response_model=OpeningPractice)
def user_opening_practice(
    user_id: int,
    storage: StorageDependency,
    family: Annotated[str, Query(min_length=1, max_length=160)],
    date_from: Annotated[str | None, Query(pattern=r"^\d{4}\.\d{2}\.\d{2}$")] = None,
    date_to: Annotated[str | None, Query(pattern=r"^\d{4}\.\d{2}\.\d{2}$")] = None,
    color: Literal["white", "black"] | None = None,
) -> OpeningPractice:
    """Create a Lichess analysis link for one common line in this opening."""
    reference = storage.get_opening_reference_game(
        user_id, family, date_from=date_from, date_to=date_to, color=color
    )
    if reference is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opening not found.")
    moves = opening_move_path(
        str(reference["pgn"]),
        reference["opening_ply"] if isinstance(reference["opening_ply"], int) else None,
    )
    if moves is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Opening moves unavailable.")
    return OpeningPractice(
        reference_opening=str(reference["opening"]),
        moves=moves,
        lichess_url=f"https://lichess.org/analysis/pgn/{quote('_'.join(moves), safe='_')}",
    )


@app.get("/api/users/{user_id}/tactics", response_model=TacticsOverview)
def user_tactics(
    user_id: int,
    storage: StorageDependency,
    date_from: Annotated[str | None, Query(pattern=r"^\d{4}\.\d{2}\.\d{2}$")] = None,
    date_to: Annotated[str | None, Query(pattern=r"^\d{4}\.\d{2}\.\d{2}$")] = None,
    color: Literal["white", "black"] | None = None,
) -> TacticsOverview:
    """Summarize clear tactical motifs from a small sample of recent losses."""
    patterns: dict[str, list[dict[str, object]]] = {}
    games = storage.get_recent_losses(user_id, date_from=date_from, date_to=date_to, color=color)
    for game in games:
        mistake = first_major_mistake(str(game.pop("pgn")), str(game.pop("player_color")))
        if mistake is not None and mistake["pattern"] != "a tactical turning point":
            patterns.setdefault(str(mistake["pattern"]), []).append({**game, **mistake})
    return TacticsOverview(sample_size=len(games), patterns=[TacticPattern(pattern=pattern, count=len(examples), examples=[TacticExample.model_validate(example) for example in examples]) for pattern, examples in sorted(patterns.items(), key=lambda item: -len(item[1]))])
