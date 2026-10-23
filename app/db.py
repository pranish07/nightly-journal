from __future__ import annotations

from sqlalchemy import MetaData, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def _enable_sqlite_foreign_keys(dbapi_connection: object, _connection_record: object) -> None:
    cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def make_engine(database_url: str, *, echo: bool = False) -> Engine:
    """Build an engine with settings appropriate for local SQLite or Neon."""

    if database_url.startswith("sqlite"):
        kwargs: dict[str, object] = {
            "echo": echo,
            "connect_args": {"check_same_thread": False},
        }
        if database_url == "sqlite://" or ":memory:" in database_url:
            kwargs["poolclass"] = StaticPool
        engine = create_engine(database_url, **kwargs)
        event.listen(engine, "connect", _enable_sqlite_foreign_keys)
        return engine

    return create_engine(
        database_url,
        echo=echo,
        pool_pre_ping=True,
        pool_size=2,
        max_overflow=2,
        pool_recycle=300,
        connect_args={"connect_timeout": 10},
    )


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
        class_=Session,
    )
