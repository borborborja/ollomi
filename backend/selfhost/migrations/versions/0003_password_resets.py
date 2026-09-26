"""Persist one-time password reset tokens."""

from alembic import op

from selfhost.db import PasswordReset

revision = "0003"
down_revision = "0002"


def upgrade():
    connection = op.get_bind()
    PasswordReset.__table__.create(connection, checkfirst=True)


def downgrade():
    connection = op.get_bind()
    PasswordReset.__table__.drop(connection, checkfirst=True)
