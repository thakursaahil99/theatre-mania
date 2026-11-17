from fastapi import APIRouter, Depends

from app.api.v1 import admin, auth, me, movies, playback, profiles, stream
from app.core.rate_limit import global_limiter

api_router = APIRouter(dependencies=[Depends(global_limiter)])
api_router.include_router(auth.router)
api_router.include_router(profiles.router)
api_router.include_router(movies.router)
api_router.include_router(me.router)
api_router.include_router(playback.router)
api_router.include_router(stream.router)
api_router.include_router(admin.router)
