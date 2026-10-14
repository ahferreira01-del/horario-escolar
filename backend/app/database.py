from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from .config import settings
from .db_base import Base


connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def bind_context(db, user_id: str = "", tenant_id: str = ""):
    """Set transaction-local scope for PostgreSQL RLS, plus explicit API authorization.

    A nested transaction or commit clears SET LOCAL, so call before each scoped unit of work.
    """
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT set_config('app.user_id', :user_id, true)"), {"user_id": user_id})
        db.execute(text("SELECT set_config('app.tenant_id', :tenant_id, true)"), {"tenant_id": tenant_id})


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
