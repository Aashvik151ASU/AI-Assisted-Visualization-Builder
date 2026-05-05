from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from backend.config import settings


class Base(DeclarativeBase):
    pass


_engine = None
_SessionLocal = None


def _get_engine():
    global _engine
    if _engine is None and settings.database_url:
        _engine = create_engine(
            settings.database_url,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
        )
    return _engine


def _get_session_factory():
    global _SessionLocal
    engine = _get_engine()
    if engine is None:
        return None
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return _SessionLocal


def get_db():
    factory = _get_session_factory()
    if factory is None:
        yield None
        return
    db = factory()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables if they do not exist yet. No-op when DATABASE_URL is unset."""
    engine = _get_engine()
    if engine is None:
        return
    import backend.models  # noqa: F401 — registers models with Base
    Base.metadata.create_all(bind=engine)


def check_connection() -> bool:
    try:
        engine = _get_engine()
        if engine is None:
            return False
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
