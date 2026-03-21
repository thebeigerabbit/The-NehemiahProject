from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
from config.settings import DATABASE_URL
from app.models import Base
import logging

logger = logging.getLogger(__name__)

engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=3600,
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def init_db():
    """Create all tables if they don't exist (used as fallback; prefer Alembic)."""
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables ensured.")


@contextmanager
def get_db() -> Session:
    """Synchronous context manager for DB sessions."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
