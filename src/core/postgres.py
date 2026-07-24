import contextlib
import functools
import typing

import sqlalchemy
import sqlalchemy.ext.asyncio


metadata = sqlalchemy.MetaData(
    naming_convention={
        'ix': 'ix_%(column_0_label)s',
        'uq': 'uq_%(table_name)s_%(column_0_name)s',
        'ck': 'ck_%(table_name)s_%(constraint_name)s',
        'fk': 'fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s',
        'pk': 'pk_%(table_name)s',
    },
)


class Error(Exception):
    """Raised for PostgreSQL lifecycle errors."""


class Database:
    _instance: typing.ClassVar['Database | None'] = None

    def __init__(
        self,
        url: str,
        pool_size: int = 5,
        max_overflow: int = 10,
    ) -> None:
        self._engine = sqlalchemy.ext.asyncio.create_async_engine(
            url,
            pool_pre_ping=True,
            pool_size=pool_size,
            max_overflow=max_overflow,
        )
        self._session_factory = sqlalchemy.ext.asyncio.async_sessionmaker(
            self._engine,
            expire_on_commit=False,
        )
        self._is_connected = False

    @property
    def is_alive(self) -> bool:
        return self._is_connected

    @classmethod
    def create(cls, *args, **kwargs) -> 'Database':
        cls._instance = cls(*args, **kwargs)
        return cls._instance

    @classmethod
    def set_instance(cls, database: 'Database') -> None:
        cls._instance = database

    @classmethod
    def instance(cls) -> 'Database':
        if cls._instance is None:
            raise Error('PostgreSQL session was not initialized')
        return cls._instance

    async def connect(self) -> None:
        if self._is_connected:
            raise Error('PostgreSQL engine was already connected')
        async with self._engine.connect() as connection:
            await connection.execute(sqlalchemy.text('SELECT 1'))
        self._is_connected = True

    async def disconnect(self) -> None:
        if not self._is_connected:
            return
        await self._engine.dispose()
        self._is_connected = False

    @contextlib.asynccontextmanager
    async def get_session(self):
        async with self._session_factory() as db_session:
            yield db_session

    async def ping(self) -> bool:
        try:
            async with self._engine.connect() as connection:
                await connection.execute(sqlalchemy.text('SELECT 1'))
        except (ConnectionError, sqlalchemy.exc.SQLAlchemyError):
            return False
        return True


def session(func):
    """Run a model function in a transaction unless a session was supplied."""

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        if args and isinstance(args[0], sqlalchemy.ext.asyncio.AsyncSession):
            return await func(*args, **kwargs)

        async with Database.instance().get_session() as db_session:
            async with db_session.begin():
                return await func(db_session, *args, **kwargs)

    return wrapper
