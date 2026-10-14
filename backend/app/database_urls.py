"""Pure PostgreSQL URL helpers shared by runtime configuration and Alembic."""


def normalize_postgres_url(url: str) -> str:
    """Select Psycopg 3 for provider URLs that omit an explicit driver."""
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url.removeprefix("postgres://")
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url.removeprefix("postgresql://")
    return url
