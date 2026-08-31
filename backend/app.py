"""FastAPI application for Chess Lab."""

import os
from io import TextIOWrapper
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import quote

from fastapi import Depends, FastAPI, HTTPException, Query, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

import chess

from backend.auth import get_principal, hosted_environment, validate_auth_configuration
from backend.request_limits import RequestSizeLimit

from chesslab import APP_NAME
from chesslab.explorer import explore_position
from chesslab.importer import iter_game_records
from chesslab.identities import validate_chess_username
from chesslab.models import GameRecord
from chesslab.openings import OpeningCatalog
from chesslab.storage import SQLiteGameStorage
from chesslab.postgres import PostgresGameStorage
from chesslab.theory import assess_pgn_opening, first_major_mistake, opening_move_path


class ImportResponse(BaseModel):
    """Compact summary returned after a PGN import."""

    games_received: int
    games_added: int
    duplicates_skipped: int
    matched_games: int | None = None


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
    moves: list[str]


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
    moves: list[str]


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
    moves: list[str]


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


class ExplorerResults(BaseModel):
    games: int
    wins: int
    draws: int
    losses: int
    unfinished: int
    score: float | None


class ExplorerExample(BaseModel):
    date: str | None
    source_url: str | None
    result: str | None


class ExplorerMove(ExplorerResults):
    uci: str
    san: str
    frequency: float
    score_change: float | None
    examples: list[ExplorerExample]


class OpeningExplorer(ExplorerResults):
    fen: str
    san_path: list[str]
    root_plies: int
    player_color: Literal["white", "black"]
    turn: Literal["white", "black"]
    ended_games: int
    skipped_games: int
    at_limit: bool
    moves: list[ExplorerMove]


class PracticePositionNotes(BaseModel):
    note: str = Field(default="", max_length=1000)
    candidate_move: str = Field(default="", max_length=20)


class CreatePracticePosition(PracticePositionNotes):
    family: str = Field(min_length=1, max_length=160)
    player_color: Literal["white", "black"]
    line: list[str] = Field(default_factory=list, max_length=24)
    date_from: str | None = Field(default=None, pattern=r"^\d{4}\.\d{2}\.\d{2}$")
    date_to: str | None = Field(default=None, pattern=r"^\d{4}\.\d{2}\.\d{2}$")


class PracticePosition(CreatePracticePosition):
    id: int
    fen: str
    san_path: list[str]
    examples: list[ExplorerExample]
    created_at: str


class SavePracticePositionResponse(BaseModel):
    position: PracticePosition
    created: bool


class RepertoireItemInput(BaseModel):
    context: str
    opening: str
    status: Literal["keep", "practice", "try"]
    note: str = ""


class RepertoireItem(RepertoireItemInput):
    id: int


validate_auth_configuration()
if hosted_environment() and not os.getenv("DATABASE_URL"):
    raise RuntimeError("Hosted deployments require PostgreSQL DATABASE_URL; SQLite is local-only.")
default_storage = PostgresGameStorage(os.environ["DATABASE_URL"]) if os.getenv("DATABASE_URL") else SQLiteGameStorage(
    Path(os.environ.get("CHESSLAB_DATABASE_PATH", "data/chesslab.db"))
)
default_opening_catalog = OpeningCatalog.from_directory(
    Path(__file__).resolve().parents[1] / "data" / "openings"
)


def get_storage() -> SQLiteGameStorage:
    """Provide the configured game storage to API routes."""
    return default_storage


StorageDependency = Annotated[SQLiteGameStorage, Depends(get_storage)]


def authorize_api(request: Request, storage: StorageDependency) -> None:
    if request.url.path == "/health":
        return
    # All API routes inherit this dependency, including future additions.
    principal = get_principal(request)
    request.state.principal = principal
    if principal is None:
        request.state.user_id = None
        return
    user_id = storage.ensure_account(principal.subject)
    request.state.user_id = user_id
    target = request.path_params.get("user_id")
    if target is not None and str(target) != str(user_id):
        raise HTTPException(404, "Not found.")
    if request.url.path.rstrip("/") == "/api/users":
        raise HTTPException(404, "Not found.")
    if request.url.path.endswith(("/theory", "/review", "/tactics")) and os.getenv("CHESSLAB_ENGINE_ENABLED") != "true":
        raise HTTPException(503, "Engine review is not enabled for this beta. Opening statistics and the explorer remain available.")


app = FastAPI(title=APP_NAME, dependencies=[Depends(authorize_api)])
app.add_middleware(RequestSizeLimit)
allowed_origins = os.environ.get("CHESSLAB_ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
app.add_middleware(CORSMiddleware,
    allow_origins=[origin.strip() for origin in allowed_origins if origin.strip()],
    allow_credentials=False, allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


class ChessIdentityInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    platform: Literal["lichess", "chess_com", "other"]
    username: str = Field(min_length=1, max_length=80)

    @field_validator('username', mode='before')
    @classmethod
    def trim_username(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator('username')
    @classmethod
    def validate_username(cls, value: str, info: ValidationInfo) -> str:
        return validate_chess_username(info.data.get('platform', ''), value)


class AccountSetup(ChessIdentityInput):
    display_name: str = Field(min_length=1, max_length=80)


class AccountIdentitiesUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    identities: list[ChessIdentityInput] = Field(min_length=1, max_length=10)


class AccountIdentitiesResult(BaseModel):
    account: UserProfile
    library_games: int
    matched_games: int


@app.get("/api/account", response_model=UserProfile)
def current_account(request: Request, storage: StorageDependency) -> UserProfile:
    user_id = request.state.user_id
    if user_id is None:
        user_id = int(os.getenv("CHESSLAB_LOCAL_USER_ID", "1"))
    profile = storage.get_user_profile(user_id)
    if profile is None:
        raise HTTPException(404, "No local profile exists.")
    return UserProfile.model_validate(profile)


@app.post("/api/account", response_model=UserProfile)
def setup_account(request: Request, details: AccountSetup, storage: StorageDependency) -> UserProfile:
    if request.state.user_id is None:
        raise HTTPException(409, "Account setup requires Google sign-in.")
    if not details.display_name.strip():
        raise HTTPException(422, "Display name is required.")
    try:
        storage.configure_account(request.state.user_id, details.display_name.strip(), details.platform, details.username)
    except ValueError as error:
        raise HTTPException(409, str(error)) from error
    return current_account(request, storage)


@app.patch('/api/account/identities', response_model=AccountIdentitiesResult)
def update_account_identities(request: Request, details: AccountIdentitiesUpdate, storage: StorageDependency):
    if request.state.user_id is None:
        raise HTTPException(409, 'Username settings require Google sign-in.')
    try:
        counts = storage.update_account_identities(request.state.user_id, [identity.model_dump() for identity in details.identities])
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    return AccountIdentitiesResult(account=current_account(request, storage), **counts)


@app.get("/health")
def health() -> dict[str, str]:
    """Report whether the API process is running."""
    return {"status": "ok"}


@app.post("/api/games/import", response_model_exclude_none=True)
async def import_games(
    request: Request,
    file: UploadFile,
    storage: StorageDependency,
) -> ImportResponse:
    """Parse and persist an uploaded PGN file, then return its game records."""
    owner = request.state.user_id
    if file.size is None or file.size > 10 * 1024 * 1024:
        raise HTTPException(413, "Choose a PGN file smaller than 10 MB.")
    identities = storage.get_user_profile(owner)['identities'] if owner is not None else []
    if owner is not None and not identities:
        raise HTTPException(409, "Set your chess username before importing games.")
    await file.seek(0)
    pgn_stream = TextIOWrapper(file.file, encoding="utf-8-sig")
    identity_keys = {(identity['platform'], identity['username'].lower()) for identity in identities}
    matched_games = 0
    try:
        def bounded_games():
            nonlocal matched_games
            for index, game in enumerate(iter_game_records(pgn_stream, default_opening_catalog)):
                if index >= 5000:
                    raise HTTPException(413, "Import at most 5,000 games at a time.")
                white_matches = (game.source, (game.white or '').lower()) in identity_keys
                black_matches = (game.source, (game.black or '').lower()) in identity_keys
                if white_matches != black_matches:
                    matched_games += 1
                yield game
        games_received, games_added = storage.import_games(bounded_games(), owner_user_id=owner)
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
        matched_games=matched_games if owner is not None else None,
    )


@app.get("/api/games", response_model=GamePage)
def list_games(
    request: Request,
    storage: StorageDependency,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> GamePage:
    """Return a bounded page of stored games in import order."""
    games = storage.list_games(limit=limit, offset=offset, owner_user_id=request.state.user_id)
    return GamePage(
        total=storage.count_games(owner_user_id=request.state.user_id),
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
    for opening in overview["top_openings"]:
        opening["moves"] = default_opening_catalog.moves_for_name(str(opening["opening"]))
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
    for opening in openings:
        opening["moves"] = default_opening_catalog.moves_for_name(str(opening["opening"]))
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
    for variation in detail["variations"]:
        variation["moves"] = default_opening_catalog.moves_for_name(str(variation["opening"]))
    return OpeningDetail.model_validate(detail)


@app.get("/api/users/{user_id}/openings/explorer", response_model=OpeningExplorer)
def user_opening_explorer(
    user_id: int,
    storage: StorageDependency,
    family: Annotated[str, Query(min_length=1, max_length=160)],
    color: Literal["white", "black"],
    line: Annotated[str, Query(max_length=150)] = "",
    date_from: Annotated[str | None, Query(pattern=r"^\d{4}\.\d{2}\.\d{2}$")] = None,
    date_to: Annotated[str | None, Query(pattern=r"^\d{4}\.\d{2}\.\d{2}$")] = None,
) -> OpeningExplorer:
    """Explore actual continuations from an opening's defining position."""
    if storage.get_user_profile(user_id) is None:
        raise HTTPException(status_code=404, detail="User not found.")
    root_moves = default_opening_catalog.moves_for_name(family)
    if not root_moves:
        raise HTTPException(status_code=404, detail="No defining move line is available for this opening.")
    try:
        # Validate the requested line before loading the archive.
        continuation = line.split(",") if line else []
        explore_position([], root_moves, continuation, color)
        result = explore_position(
            storage.get_explorer_games(user_id, color=color, date_from=date_from, date_to=date_to),
            root_moves, continuation, color,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail="Invalid or excessively long move continuation.") from error
    return OpeningExplorer.model_validate(result)


def validated_candidate_move(fen: str, candidate: str) -> str:
    """Keep optional study moves legal for the side to move, in normalized SAN."""
    if not candidate.strip():
        return ""
    board = chess.Board(fen)
    try:
        move = board.parse_san(candidate.strip())
        if not move or move not in board.legal_moves:
            raise ValueError("Illegal move")
        return board.san(move)
    except ValueError as error:
        raise HTTPException(status_code=422, detail="Move to try must be legal in this position (SAN, e.g. Nf3).") from error


@app.get("/api/users/{user_id}/practice-positions", response_model=list[PracticePosition])
def list_practice_positions(user_id: int, storage: StorageDependency) -> list[PracticePosition]:
    if storage.get_user_profile(user_id) is None:
        raise HTTPException(status_code=404, detail="User not found.")
    return [PracticePosition.model_validate(item) for item in storage.list_practice_positions(user_id)]


@app.post("/api/users/{user_id}/practice-positions", response_model=SavePracticePositionResponse)
def save_practice_position(user_id: int, request: CreatePracticePosition, storage: StorageDependency) -> SavePracticePositionResponse:
    if storage.get_user_profile(user_id) is None:
        raise HTTPException(status_code=404, detail="User not found.")
    root = default_opening_catalog.moves_for_name(request.family)
    if not root:
        raise HTTPException(status_code=404, detail="Opening not found.")
    try:
        position = explore_position([], root, request.line, request.player_color)
    except ValueError as error:
        raise HTTPException(status_code=422, detail="Invalid move continuation.") from error
    candidate = validated_candidate_move(position["fen"], request.candidate_move)
    result = explore_position(
        storage.get_explorer_games(user_id, color=request.player_color, date_from=request.date_from, date_to=request.date_to),
        root, request.line, request.player_color,
    )
    examples = []
    seen_urls = set()
    for branch in result["moves"]:
        for example in branch["examples"]:
            url = example["source_url"]
            if isinstance(url, str) and url.startswith(("https://", "http://")) and url not in seen_urls:
                examples.append(example)
                seen_urls.add(url)
    saved, created = storage.save_practice_position(user_id, {
        **request.model_dump(), "note": request.note.strip(), "candidate_move": candidate,
        "fen": position["fen"], "position_key": chess.Board(position["fen"]).epd(),
        "san_path": position["san_path"], "examples": examples[:3],
    })
    return SavePracticePositionResponse(position=PracticePosition.model_validate(saved), created=created)


@app.patch("/api/users/{user_id}/practice-positions/{position_id}", response_model=PracticePosition)
def update_practice_position(user_id: int, position_id: int, request: PracticePositionNotes, storage: StorageDependency) -> PracticePosition:
    existing = storage.get_practice_position(user_id, position_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Practice position not found.")
    candidate = validated_candidate_move(str(existing["fen"]), request.candidate_move)
    saved = storage.update_practice_position(user_id, position_id, request.note.strip(), candidate)
    if saved is None:
        raise HTTPException(status_code=404, detail="Practice position not found.")
    return PracticePosition.model_validate(saved)


@app.delete("/api/users/{user_id}/practice-positions/{position_id}", status_code=204)
def delete_practice_position(user_id: int, position_id: int, storage: StorageDependency) -> None:
    if not storage.delete_practice_position(user_id, position_id):
        raise HTTPException(status_code=404, detail="Practice position not found.")


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
