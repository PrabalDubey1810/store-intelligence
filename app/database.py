from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
import os, logging

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://admin:secret@localhost:5432/store_intel")

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    connect_args={"connect_timeout": 10},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

logger = logging.getLogger(__name__)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_db_health() -> dict:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "connected"}
    except Exception as e:
        logger.error("DB health check failed", exc_info=True)
        return {"status": "error", "detail": str(e)}
