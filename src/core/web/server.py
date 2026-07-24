import uvicorn


def create_server(app, host: str, port: int):
    return uvicorn.Server(
        uvicorn.Config(
            app,
            host=host,
            port=port,
            server_header=False,
        ),
    )
