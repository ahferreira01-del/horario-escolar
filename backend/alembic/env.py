"""Migrações versionadas: execução EXCLUSIVA pela conta proprietária/migradora."""
import os
from logging.config import fileConfig
from alembic import context
from sqlalchemy import engine_from_config, pool
from app.config import normalize_postgres_url, settings
from app.database import Base
import app.models  # noqa: F401 -- registra todas as tabelas

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)
if settings.environment == "production":
    migration_database_url = os.environ.get("HI_MIGRATION_DATABASE_URL", "").strip()
    if not migration_database_url:
        raise RuntimeError("HI_MIGRATION_DATABASE_URL is required before production migrations")
    migration_database_url = normalize_postgres_url(migration_database_url)
else:
    migration_database_url = settings.database_url
config.set_main_option('sqlalchemy.url', migration_database_url.replace('%','%%'))
target_metadata = Base.metadata

def run_migrations_offline():
    context.configure(url=migration_database_url, target_metadata=target_metadata,
                      literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    connectable = engine_from_config(config.get_section(config.config_ini_section),
                                     prefix='sqlalchemy.', poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata,
                          compare_type=True, render_as_batch=connection.dialect.name=='sqlite')
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
