from alembic import context
from sqlalchemy import create_engine, pool

from finsight.config import settings
from finsight.storage import Base

config = context.config
url = settings().db_url
if context.is_offline_mode():
    context.configure(url=url,target_metadata=Base.metadata,literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(url,poolclass=pool.NullPool,connect_args={"connect_timeout":5})
    with engine.connect() as conn:
        context.configure(connection=conn,target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()
