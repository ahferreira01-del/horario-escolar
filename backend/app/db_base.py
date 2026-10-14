"""SQLAlchemy model metadata without importing runtime database settings."""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
