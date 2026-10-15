from alembic import context

from backend.db.models import (
    Base,
    chat,  # noqa: F401
    jobs,  # noqa: F401
    parsing,  # noqa: F401
    plugins,  # noqa: F401
    reviews,  # noqa: F401
    workspace,  # noqa: F401
)

connection = context.config.attributes["connection"]
context.configure(connection=connection, target_metadata=Base.metadata, render_as_batch=True)
with context.begin_transaction():
    context.run_migrations()
