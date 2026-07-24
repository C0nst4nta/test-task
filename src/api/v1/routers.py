import fastapi

from .endpoints import run


def get_router() -> fastapi.APIRouter:
    router = fastapi.APIRouter(prefix='/v1')
    router.include_router(run.router, tags=['Synchronization'])
    return router
