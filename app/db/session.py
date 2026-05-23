from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False}
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """
    FastAPI dependency that yields a database session per request,
    then closes it automatically when the request is done.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()