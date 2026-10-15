import os

from sqlalchemy import create_engine

from alembic import context

# Migrations run as the owner role; the API never holds these credentials.
engine = create_engine(os.environ["OWNER_DATABASE_URL"])

with engine.connect() as connection:
    context.configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()
