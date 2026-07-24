import fastapi


async def request_validation_exception_handler(
    request: fastapi.Request,
    exc: fastapi.exceptions.RequestValidationError,
) -> fastapi.responses.Response:
    return fastapi.responses.ORJSONResponse(
        status_code=422,
        content={
            'detail': [
                {
                    'loc': error['loc'],
                    'msg': error['msg'],
                    'type': error['type'],
                }
                for error in exc.errors()
            ],
        },
    )


def create_app(
    title: str,
    lifespan=None,
    routers: list[fastapi.APIRouter] | None = None,
    debug: bool = False,
) -> fastapi.FastAPI:
    app = fastapi.FastAPI(
        title=title,
        version='0.1.0',
        debug=debug,
        lifespan=lifespan,
        default_response_class=fastapi.responses.ORJSONResponse,
        redoc_url=None,
    )

    for router in routers or []:
        app.include_router(router)

    app.add_exception_handler(
        fastapi.exceptions.RequestValidationError,
        request_validation_exception_handler,
    )
    return app
