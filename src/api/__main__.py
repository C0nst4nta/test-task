import logging

from ..core import conf
from ..core import web
from . import create_app


def main() -> None:
    settings = conf.get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    )
    server = web.create_server(
        create_app(settings),
        host=settings.app_host,
        port=settings.app_port,
    )
    server.run()


if __name__ == '__main__':
    main()
