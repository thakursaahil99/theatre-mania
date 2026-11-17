import os

# Must be set before the app (and its settings singleton) is imported.
os.environ.update(
    {
        "APP_ENV_FILE": "__tests_ignore_dotenv__",  # never inherit the developer's backend/.env
        "ENV": "test",
        "DATABASE_URL": "sqlite+aiosqlite://",
        "JWT_SECRET": "test-secret-that-is-definitely-long-enough-123",
        "TMDB_READ_TOKEN": "test-token",
        "ADMIN_EMAILS": "admin@example.com",
        "FRONTEND_URL": "http://localhost:3000",
        "CORS_ORIGINS": "http://localhost:3000",
    }
)

from typing import Any  # noqa: E402

import fakeredis.aioredis  # noqa: E402
import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.api.deps import get_tmdb  # noqa: E402
from app.core.database import get_db  # noqa: E402
from app.core.redis import set_redis  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402
from app.services.tmdb import TMDBClient, TMDBNotFound  # noqa: E402

MISSING_ID = 999999


def tmdb_movie(mid: int, title: str | None = None, **extra: Any) -> dict[str, Any]:
    return {
        "id": mid,
        "title": title or f"Movie {mid}",
        "original_title": title or f"Movie {mid}",
        "overview": "An overview.",
        "poster_path": f"/poster{mid}.jpg",
        "backdrop_path": f"/backdrop{mid}.jpg",
        "release_date": "1968-10-01",
        "vote_average": 7.5,
        "vote_count": 1000,
        "popularity": 50.0,
        "genre_ids": [27],
        "original_language": "en",
        **extra,
    }


def tmdb_detail(mid: int) -> dict[str, Any]:
    return tmdb_movie(
        mid,
        title="Night of the Living Dead" if mid == 10331 else None,
        genres=[{"id": 27, "name": "Horror"}],
        runtime=96,
        tagline="They won't stay dead!",
        imdb_id="tt0063350",
        videos={"results": [
            {"key": "teaser1", "site": "YouTube", "type": "Teaser", "name": "Teaser", "official": True, "iso_639_1": "en"},
            {"key": "trailer1", "site": "YouTube", "type": "Trailer", "name": "Official Trailer", "official": True,
             "iso_639_1": "en"},
        ]},
        credits={"cast": [{"id": 1, "name": "Duane Jones", "character": "Ben", "order": 0, "profile_path": None}],
                 "crew": [{"id": 2, "name": "George A. Romero", "job": "Director"}]},
        similar={"results": [tmdb_movie(2001), tmdb_movie(2002)]},
        recommendations={"results": []},
        release_dates={"results": [{"iso_3166_1": "US", "release_dates": [{"certification": "R", "type": 3}]}]},
        **{"watch/providers": {"results": {"US": {
            "link": "https://www.themoviedb.org/movie/10331/watch",
            "flatrate": [{"provider_id": 8, "provider_name": "Netflix", "logo_path": "/n.jpg", "display_priority": 1}],
        }}}},
    )  # fmt: skip


class FakeTMDB(TMDBClient):
    def __init__(self, redis):
        super().__init__(http=None, redis=redis)  # type: ignore[arg-type]
        self.calls: list[str] = []
        self.requests: list[tuple[str, dict[str, Any]]] = []
        self.is_enabled = True  # tests flip this to exercise the "no TMDB key" paths

    @property
    def enabled(self) -> bool:
        return self.is_enabled

    async def _get(self, path: str, params: dict[str, Any] | None = None, ttl: int | None = None) -> Any:
        self.calls.append(path)
        params = params or {}
        self.requests.append((path, params))
        parts = path.strip("/").split("/")
        if parts[0] == "movie" and parts[1].isdigit():
            mid = int(parts[1])
            if mid == MISSING_ID:
                raise TMDBNotFound(path)
            if len(parts) == 3 and parts[2] == "videos":
                return tmdb_detail(mid)["videos"]
            return tmdb_detail(mid)
        if parts[0] == "search":
            q = params.get("query", "").lower()
            results = [m for m in [tmdb_movie(10331, "Night of the Living Dead"), tmdb_movie(3085, "His Girl Friday",
                       genre_ids=[35], original_language="en")] if q in m["title"].lower()]  # fmt: skip
            return {"page": 1, "results": results, "total_pages": 1, "total_results": len(results)}
        if parts[0] == "discover" and params.get("with_original_language") == "hi":
            results = [tmdb_movie(19666, "Dilwale Dulhania Le Jayenge", original_language="hi", genre_ids=[10749]),
                       tmdb_movie(20453, "3 Idiots", original_language="hi", genre_ids=[35])]  # fmt: skip
            return {"page": params.get("page", 1), "results": results, "total_pages": 3, "total_results": 2}
        if parts[0] == "genre":
            return {"genres": [{"id": 27, "name": "Horror"}, {"id": 35, "name": "Comedy"}]}
        # trending / now_playing / top_rated / discover / popular
        return {"page": 1, "results": [tmdb_movie(10331, "Night of the Living Dead"), tmdb_movie(1002), tmdb_movie(1003)],
                "total_pages": 1, "total_results": 3}  # fmt: skip


@pytest.fixture
async def redis():
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    set_redis(client)
    yield client
    await client.flushall()


@pytest.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    await engine.dispose()


@pytest.fixture
async def tmdb(redis):
    return FakeTMDB(redis)


@pytest.fixture
async def client(session_factory, redis, tmdb):
    async def override_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_tmdb] = lambda: tmdb
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
        yield c
    app.dependency_overrides.clear()


async def signup(client: AsyncClient, email: str = "viewer@example.com", password: str = "popcorn-42") -> dict:
    resp = await client.post("/api/v1/auth/signup", json={"email": email, "password": password})
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.fixture
async def user_client(client):
    await signup(client)
    return client


@pytest.fixture
async def admin_client(client):
    await signup(client, email="admin@example.com")
    return client
