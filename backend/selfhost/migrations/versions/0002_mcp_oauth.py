"""Persist self-hosted MCP personal keys and OAuth grants."""

from alembic import op

from selfhost.db import McpApiKey, McpOauthClient, McpOauthCode, McpOauthToken

revision = "0002"
down_revision = "0001"


def upgrade():
    connection = op.get_bind()
    for table in (
        McpApiKey.__table__,
        McpOauthClient.__table__,
        McpOauthCode.__table__,
        McpOauthToken.__table__,
    ):
        table.create(connection, checkfirst=True)


def downgrade():
    connection = op.get_bind()
    for table in (
        McpOauthToken.__table__,
        McpOauthCode.__table__,
        McpOauthClient.__table__,
        McpApiKey.__table__,
    ):
        table.drop(connection, checkfirst=True)
