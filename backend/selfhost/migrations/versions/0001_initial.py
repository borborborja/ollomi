"""Ollomi local identity, records, job ledger and vector search."""

from alembic import op
from selfhost.db import Base

revision = "0001"
down_revision = None


def upgrade():
    connection = op.get_bind()
    Base.metadata.create_all(connection)
    if connection.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
        op.execute(
            "CREATE TABLE embeddings (record_id VARCHAR(36) NOT NULL REFERENCES records(id) ON DELETE CASCADE, user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE, generation VARCHAR(32) NOT NULL, chunk_index INTEGER NOT NULL, content TEXT NOT NULL, embedding VECTOR NOT NULL, PRIMARY KEY(record_id,generation,chunk_index))"
        )
        op.execute(
            "CREATE INDEX embeddings_owner_generation ON embeddings(user_id,generation)"
        )


def downgrade():
    op.execute("DROP TABLE IF EXISTS embeddings")
    Base.metadata.drop_all(op.get_bind())
