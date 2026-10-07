"""report ai human score

- discussion_reports.ai_human_score: AI 참가자와 사람 참가자 사이의 쌍별 일치도

Revision ID: 529432c5de3e
Revises: 21000d7653c7
Create Date: 2026-10-07 09:15:20.369446

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '529432c5de3e'
down_revision: Union[str, Sequence[str], None] = '21000d7653c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('discussion_reports', schema=None) as batch_op:
        batch_op.add_column(sa.Column('ai_human_score', sa.Float(), nullable=True))



def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('discussion_reports', schema=None) as batch_op:
        batch_op.drop_column('ai_human_score')

