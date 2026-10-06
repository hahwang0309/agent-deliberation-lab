"""user roles and status

- users: role(user|admin), status(pending|active|suspended|rejected), must_change_password,
  token_version, 승인 정보, 사용자별 실행 제한 추가
- 기존 사용자는 role=user, is_active=False면 suspended 아니면 active로 변환 후 구독·인증 관련 컬럼 제거

Revision ID: 21000d7653c7
Revises: 3a306e0e4301
Create Date: 2026-10-06 23:32:49.053404

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '21000d7653c7'
down_revision: Union[str, Sequence[str], None] = '3a306e0e4301'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('role', sa.String(length=20), nullable=False, server_default='user'))
        batch_op.add_column(sa.Column('status', sa.String(length=20), nullable=False, server_default='active'))
        batch_op.add_column(sa.Column('must_change_password', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('token_version', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('signup_note', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('approved_by', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('max_concurrent', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('daily_limit', sa.Integer(), nullable=True))

    op.get_bind().execute(sa.text("UPDATE users SET status = 'suspended' WHERE is_active = :false"), {"false": False})

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('subscription_expires_at')
        batch_op.drop_column('is_active')
        batch_op.drop_column('is_verified')
        batch_op.drop_column('subscription_plan')


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('subscription_plan', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('is_verified', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('is_active', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('subscription_expires_at', sa.DateTime(), nullable=True))

    op.get_bind().execute(sa.text("UPDATE users SET is_active = (status = 'active'), subscription_plan = 'free'"))

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('daily_limit')
        batch_op.drop_column('max_concurrent')
        batch_op.drop_column('approved_at')
        batch_op.drop_column('approved_by')
        batch_op.drop_column('signup_note')
        batch_op.drop_column('token_version')
        batch_op.drop_column('must_change_password')
        batch_op.drop_column('status')
        batch_op.drop_column('role')
