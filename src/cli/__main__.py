import pathlib
import sys

import alembic.config


def main() -> None:
    ini_path = pathlib.Path(__file__).parents[1] / 'migrations' / 'postgres' / 'alembic.ini'
    alembic.config.CommandLine().main(argv=['-c', str(ini_path), *sys.argv[1:]])


if __name__ == '__main__':
    main()
