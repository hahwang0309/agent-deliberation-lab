"""discussion runtime schema

- 행정조사 분석 테이블(investigation_analyses, batch_analyses, batch_analysis_items)을
  data/legacy_export/에 JSON으로 내보낸 뒤 삭제
- discussions: 런타임 상태·소주제·LLM 사용량·중지 정보 컬럼 추가, 미사용 컬럼 제거, 상태 값 변환
- messages: seq(토론 내 순번)·speaker_type·user_id·action·meta 추가, 기존 메시지 seq 백필

Revision ID: 3bec9df124c9
Revises: 115ef33629d0
Create Date: 2026-10-06 21:35:39.512408

"""
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3bec9df124c9'
down_revision: Union[str, Sequence[str], None] = '115ef33629d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")

LEGACY_TABLES = ("batch_analysis_items", "batch_analyses", "investigation_analyses")  # FK 순서
EXPORT_DIR = Path(os.getenv("LEGACY_EXPORT_DIR") or Path(__file__).resolve().parents[2] / "data" / "legacy_export")

# 기존 상태 값 → 새 상태 값
STATUS_MAP = {
    "initialized": "draft",
    "paused": "interrupted",
    "running": "interrupted",
}


def _export_and_drop_legacy_tables(bind) -> None:
    existing = set(sa.inspect(bind).get_table_names())
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    for table in LEGACY_TABLES:
        if table not in existing:
            continue
        rows = [dict(r) for r in bind.execute(sa.text(f"SELECT * FROM {table}")).mappings()]
        if rows:
            EXPORT_DIR.mkdir(parents=True, exist_ok=True)
            path = EXPORT_DIR / f"{table}_{stamp}.json"
            path.write_text(json.dumps(rows, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            logger.warning("Exported %d rows from %s to %s", len(rows), table, path)
        op.drop_table(table)


def upgrade() -> None:
    bind = op.get_bind()

    # 1. 행정조사 분석 테이블 내보내기 후 삭제
    _export_and_drop_legacy_tables(bind)

    # 2. discussions
    with op.batch_alter_table('discussions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('language', sa.String(length=10), nullable=True))
        batch_op.add_column(sa.Column('error', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('last_seq', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('subtopics', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('prompt_tokens', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('completion_tokens', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('llm_calls', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('stopped_by', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('stop_reason', sa.Text(), nullable=True))
        batch_op.drop_column('consensus_reached')
        batch_op.drop_column('resumed_at')
        batch_op.drop_column('current_round')
        batch_op.drop_column('paused_at')
        batch_op.drop_column('total_rounds')

    for old, new in STATUS_MAP.items():
        bind.execute(sa.text("UPDATE discussions SET status = :new WHERE status = :old"), {"old": old, "new": new})

    # 3. messages: 컬럼 추가 (seq는 백필 후 NOT NULL)
    with op.batch_alter_table('messages', schema=None) as batch_op:
        batch_op.add_column(sa.Column('seq', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('speaker_type', sa.String(length=20), nullable=False, server_default='ai'))
        batch_op.add_column(sa.Column('user_id', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('action', sa.String(length=30), nullable=True))
        batch_op.add_column(sa.Column('meta', sa.JSON(), nullable=True))
        batch_op.alter_column('speaker_id', existing_type=sa.String(), nullable=True)

    # 기존 메시지 seq 백필 (토론별 시간순 1..N)
    rows = bind.execute(sa.text(
        "SELECT id, discussion_id FROM messages ORDER BY discussion_id, round_number, message_order, timestamp, id"
    )).fetchall()
    counters = {}
    for msg_id, discussion_id in rows:
        counters[discussion_id] = counters.get(discussion_id, 0) + 1
        bind.execute(sa.text("UPDATE messages SET seq = :seq WHERE id = :id"),
                     {"seq": counters[discussion_id], "id": msg_id})
    for discussion_id, last_seq in counters.items():
        bind.execute(sa.text("UPDATE discussions SET last_seq = :s WHERE id = :d"),
                     {"s": last_seq, "d": discussion_id})

    with op.batch_alter_table('messages', schema=None) as batch_op:
        batch_op.alter_column('seq', existing_type=sa.Integer(), nullable=False)
        batch_op.create_index('ux_messages_discussion_seq', ['discussion_id', 'seq'], unique=True)
        batch_op.drop_column('rag_classification')
        batch_op.drop_column('word_count')
        batch_op.drop_column('sentiment_label')
        batch_op.drop_column('sentence_count')
        batch_op.drop_column('message_order')
        batch_op.drop_column('round_number')
        batch_op.drop_column('sentiment_score')
        batch_op.drop_column('sentiment_confidence')
        batch_op.drop_column('character_count')


def downgrade() -> None:
    """스키마만 되돌린다. 삭제된 행정조사 테이블 데이터는 data/legacy_export/의 JSON에 남아 있다."""
    with op.batch_alter_table('messages', schema=None) as batch_op:
        batch_op.add_column(sa.Column('character_count', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('sentiment_confidence', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('sentiment_score', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('round_number', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('message_order', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('sentence_count', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('sentiment_label', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('word_count', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('rag_classification', sa.String(length=50), nullable=True))
        batch_op.drop_index('ux_messages_discussion_seq')
        batch_op.drop_column('meta')
        batch_op.drop_column('action')
        batch_op.drop_column('user_id')
        batch_op.drop_column('speaker_type')
        batch_op.drop_column('seq')

    with op.batch_alter_table('discussions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('total_rounds', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('paused_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('current_round', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('resumed_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('consensus_reached', sa.Boolean(), nullable=True))
        batch_op.drop_column('stop_reason')
        batch_op.drop_column('stopped_by')
        batch_op.drop_column('llm_calls')
        batch_op.drop_column('completion_tokens')
        batch_op.drop_column('prompt_tokens')
        batch_op.drop_column('subtopics')
        batch_op.drop_column('last_seq')
        batch_op.drop_column('error')
        batch_op.drop_column('language')

    for old, new in STATUS_MAP.items():
        if old != "running":
            op.get_bind().execute(sa.text("UPDATE discussions SET status = :old WHERE status = :new"),
                                  {"old": old, "new": new})
