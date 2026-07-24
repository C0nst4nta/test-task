import fastapi

from .endpoints import sync_runs


def get_router() -> fastapi.APIRouter:
    router = fastapi.APIRouter(prefix='/v1')
    router.include_router(sync_runs.router, tags=['Synchronization'])
    return router
