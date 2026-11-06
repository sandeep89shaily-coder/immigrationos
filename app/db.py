from uuid import UUID

from sqlalchemy import create_engine, text, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.settings import get_settings


class Base(DeclarativeBase):
    pass


def create_db_engine(url: str):
    if url.startswith("sqlite"):
        sqlite_engine = create_engine(url, future=True, connect_args={"check_same_thread": False}, poolclass=StaticPool)
        @event.listens_for(sqlite_engine, "connect")
        def enforce_sqlite_fk(connection, record):
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
        return sqlite_engine
    return create_engine(url, pool_pre_ping=True, future=True)


engine = create_db_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    with SessionLocal() as session:
        yield session


def set_db_context(db: Session, principal_sub: str, org_id: UUID | None = None):
    """Transaction-local PostgreSQL variables consumed by RLS policies.

    MUST execute before any tenant-scoped query in the same transaction.
    SQLite is used only by unit tests, never a deployed backend.
    """
    if db.bind is None or db.bind.dialect.name != "postgresql":
        return
    db.execute(text("SELECT set_config('app.principal_sub', :sub, true)"), {"sub": principal_sub})
    if org_id is not None:
        db.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": str(org_id)})
